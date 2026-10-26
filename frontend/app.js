// Стан додатку
const state = {
  cards: [],
  categories: [],
  uiTheme: localStorage.getItem("du_ui_theme") || "v2", // "v1" | "v2" | "v3"
  focusedCardIndex: 0,
  activeTab: "all", // "all" | "word_list" | "grammar_topic" | "builder"
  selectedCategory: "all",
  searchQuery: "",
  showSatzklammer: true,
  expandAllNotes: false,

  // Стан фонового аудіо-плеєра
  playlist: [],
  currentTrackIndex: 0,
  isPlayingPodcast: false,
  podcastAbortController: null,
  currentAudio: null,
  currentAudioResolve: null,
};

// Шаблони для швидкого вибору граматичних підтем у конструкторі
const GRAMMAR_PRESETS = {
  preset_strong_e_i: {
    mode: "grammar_topic",
    category: "Сильні дієслова · Чергування e → i / ie",
    words:
      "geben (du gibst), helfen (du hilfst), sprechen (du sprichst), sehen (du siehst), nehmen (du nimmst), lesen (du liest), vergessen (du vergisst). Фокус: зміна кореневої голосної у 2-й і 3-й особі однини Präsens та форма Partizip II у Perfekt.",
  },
  preset_strong_a_ae: {
    mode: "grammar_topic",
    category: "Сильні дієслова · Чергування a → ä",
    words:
      "fahren (du fährst, ist gefahren), schlafen (du schläfst), tragen (du trägst), waschen (du wäschst), einladen (du lädst ein). Фокус: умляут у Präsens (du/er) та різниця допоміжних дієслів haben vs sein у Perfekt.",
  },
  preset_modals: {
    mode: "grammar_topic",
    category: "Модальні дієслова · Рамка та Präteritum",
    words:
      "können, müssen, wollen, dürfen, sollen, mögen/möchten. Фокус: 1) відсутність закінчення в 1 і 3 ос. однини (ich/er kann, muss), 2) модальна рамка речення (Satzklammer), 3) форма Präteritum (konnte, musste, wollte).",
  },
  preset_dativ_verbs: {
    mode: "grammar_topic",
    category: "Дієслова з керуванням · + Dativ",
    words:
      "helfen (допомагати), danken (дякувати), gehören (належати), gefallen (подобатися), antworten (відповідати), passen (пасувати), vertrauen (довіряти). Фокус: вживання іменників і займенників (mir, dir, ihm, dem Mann, der Frau) у Dativ.",
  },
  preset_rektion: {
    mode: "grammar_topic",
    category: "Дієслова з прийменниками (Rektion)",
    words:
      "warten auf + Akk (чекати на), denken an + Akk (думати про), sich freuen auf + Akk (радіти майбутньому) vs sich freuen über + Akk (радіти теперішньому), träumen von + Dat (мріяти про), bitten um + Akk (просити про). Показати також питання W-Frage (Worauf? / Auf wen?).",
  },
  preset_wechsel: {
    mode: "grammar_topic",
    category: "Wechselpräpositionen · Wo? (Dat) vs Wohin? (Akk)",
    words:
      "Пари дієслів та прийменники in, auf, an, unter, über, vor, hinter, neben, zwischen: liegen/legen, stehen/stellen, sitzen/setzen, hängen. Показати контраст: де? (Wo? + Dativ) проти куди? (Wohin? + Akkusativ).",
  },
};

// Елементи DOM
const cardsGrid = document.getElementById("cards-grid");
const categorySelect = document.getElementById("category-select");
const searchInput = document.getElementById("search-input");
const wordPopup = document.getElementById("word-popup");
let popupHideTimeout = null;

// Ініціалізація
document.addEventListener("DOMContentLoaded", async () => {
  applyUITheme(state.uiTheme);
  bindUIEvents();
  await loadCards();
});

function applyUITheme(theme) {
  state.uiTheme = theme;
  localStorage.setItem("du_ui_theme", theme);
  document.body.setAttribute("data-ui-theme", theme);

  document.querySelectorAll(".ui-switch-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.theme === theme);
  });

  syncFocusModeVisibility();
}

function bindUIEvents() {
  // Перемикач 3 варіантів інтерфейсу
  document.querySelectorAll(".ui-switch-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      applyUITheme(btn.dataset.theme);
    });
  });

  // Кнопки навігації по словах у Варіанті 2 («Дружелюбний фокус»)
  document.getElementById("btn-focus-prev").addEventListener("click", () => {
    if (!state.cards.length) return;
    state.focusedCardIndex =
      (state.focusedCardIndex - 1 + state.cards.length) % state.cards.length;
    syncFocusModeVisibility();
  });

  document.getElementById("btn-focus-next").addEventListener("click", () => {
    if (!state.cards.length) return;
    state.focusedCardIndex = (state.focusedCardIndex + 1) % state.cards.length;
    syncFocusModeVisibility();
  });

  // Вкладки режимів
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.dataset.tab;
      state.activeTab = tab;

      const studyView = document.getElementById("study-view");
      const studyControls = document.getElementById("study-controls");
      const builderView = document.getElementById("builder-view");

      if (tab === "builder") {
        studyView.classList.add("hidden");
        studyControls.classList.add("hidden");
        builderView.classList.remove("hidden");
      } else {
        studyView.classList.remove("hidden");
        studyControls.classList.remove("hidden");
        builderView.classList.add("hidden");
        state.selectedCategory = "all";
        categorySelect.value = "all";
        loadCards();
      }
    });
  });

  // Фільтр категорії та пошук
  categorySelect.addEventListener("change", () => {
    state.selectedCategory = categorySelect.value;
    state.focusedCardIndex = 0;
    loadCards();
  });

  let searchTimer = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.searchQuery = searchInput.value.trim();
      state.focusedCardIndex = 0;
      loadCards();
    }, 220);
  });

  // Тогли відображення та швидкий запуск рандому по 3 речення
  const quickRandomBtn = document.getElementById("btn-quick-random3");
  if (quickRandomBtn) {
    quickRandomBtn.addEventListener("click", () => {
      const patternSel = document.getElementById("audio-pattern-select");
      patternSel.value = "random_word_3";
      rebuildPlaylist(true);
      state.currentTrackIndex = 0;
      restartPodcastLoopFromCurrent();
    });
  }

  document.getElementById("audio-pattern-select").addEventListener("change", (e) => {
    const isRandom = e.target.value === "random_word_3";
    rebuildPlaylist(isRandom);
    state.currentTrackIndex = 0;
    if (state.isPlayingPodcast) {
      restartPodcastLoopFromCurrent();
    }
  });

  document.getElementById("toggle-satzklammer").addEventListener("change", (e) => {
    state.showSatzklammer = e.target.checked;
  });

  document.getElementById("toggle-tags").addEventListener("change", (e) => {
    document.body.classList.toggle("hide-grammar-tags", !e.target.checked);
  });

  document.getElementById("btn-expand-all").addEventListener("click", () => {
    state.expandAllNotes = !state.expandAllNotes;
    document.querySelectorAll(".complexity-details").forEach((el) => {
      el.open = state.expandAllNotes;
    });
    document.getElementById("btn-expand-all").textContent = state.expandAllNotes
      ? "▼ Згорнути пояснення"
      : "► Усі пояснення";
  });

  // Попап слова — не ховати, поки курсор на самому попапі
  wordPopup.addEventListener("mouseenter", () => {
    clearTimeout(popupHideTimeout);
  });
  wordPopup.addEventListener("mouseleave", () => {
    scheduleHidePopup();
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".word-token") && !e.target.closest("#word-popup")) {
      hidePopupImmediate();
    }
  });

  // Плеєр
  document.getElementById("btn-play-pause").addEventListener("click", togglePodcastPlayback);
  document.getElementById("btn-prev").addEventListener("click", () => skipPodcastTrack(-1));
  document.getElementById("btn-next").addEventListener("click", () => skipPodcastTrack(1));

  // Гарячі клавіші (Пробіл / Стрілки)
  document.addEventListener("keydown", (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
    if (e.code === "Space") {
      e.preventDefault();
      togglePodcastPlayback();
    } else if (e.code === "ArrowRight") {
      skipPodcastTrack(1);
    } else if (e.code === "ArrowLeft") {
      skipPodcastTrack(-1);
    }
  });

  // AI Конструктор
  document.querySelectorAll('input[name="gen-mode"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      document
        .getElementById("rc-wordlist")
        .classList.toggle("active", radio.value === "word_list" && radio.checked);
      document
        .getElementById("rc-grammar")
        .classList.toggle("active", radio.value === "grammar_topic" && radio.checked);
    });
  });

  document.getElementById("preset-select").addEventListener("change", (e) => {
    const preset = GRAMMAR_PRESETS[e.target.value];
    if (!preset) return;
    const radio = document.querySelector(`input[name="gen-mode"][value="${preset.mode}"]`);
    if (radio) {
      radio.checked = true;
      radio.dispatchEvent(new Event("change"));
    }
    document.getElementById("builder-category").value = preset.category;
    document.getElementById("builder-words").value = preset.words;
  });

  document.getElementById("btn-generate-prompt").addEventListener("click", handleGeneratePrompt);
  document.getElementById("btn-copy-prompt").addEventListener("click", handleCopyPrompt);
  document.getElementById("btn-import-json").addEventListener("click", handleImportJson);
  document.getElementById("btn-regenerate-all-tts").addEventListener("click", handleRegenerateAllTTS);
}

// Завантаження карток з бекенду
async function loadCards() {
  const params = new URLSearchParams();
  if (state.activeTab === "word_list" || state.activeTab === "grammar_topic") {
    params.set("pack_type", state.activeTab);
  }
  if (state.selectedCategory && state.selectedCategory !== "all") {
    params.set("category", state.selectedCategory);
  }
  if (state.searchQuery) {
    params.set("search", state.searchQuery);
  }

  const res = await fetch(`/api/cards?${params.toString()}`);
  const data = await res.json();

  state.cards = data.cards || [];
  state.categories = data.categories || [];
  document.getElementById("count-all").textContent = data.total_cards || 0;

  if (state.focusedCardIndex >= state.cards.length) {
    state.focusedCardIndex = 0;
  }

  renderCategoryOptions();
  renderCards();
  renderFocusSidebar();
  syncFocusModeVisibility();
  rebuildPlaylist();
}

function renderCategoryOptions() {
  const current = state.selectedCategory;
  categorySelect.innerHTML = `<option value="all">Усі категорії (${state.categories.length})</option>`;
  state.categories.forEach((cat) => {
    const opt = document.createElement("option");
    opt.value = cat;
    opt.textContent = cat;
    if (cat === current) opt.selected = true;
    categorySelect.appendChild(opt);
  });
}

// Боковий список слів та прогрес-точки для Варіанта 2 («Дружелюбний фокус»)
function renderFocusSidebar() {
  const listEl = document.getElementById("focus-word-list");
  const dotsEl = document.getElementById("focus-dots");
  listEl.innerHTML = "";
  dotsEl.innerHTML = "";

  state.cards.forEach((card, idx) => {
    const item = document.createElement("div");
    item.className = "focus-word-item";
    item.dataset.idx = idx;
    item.innerHTML = `
      <div class="focus-word-item-main">
        <span class="focus-word-de">${escapeHtml(card.headword)}</span>
        <span class="focus-word-uk">${escapeHtml(card.translation)}</span>
      </div>
      <span class="focus-word-type-dot" title="${escapeAttr(card.category)}"></span>
    `;
    item.addEventListener("click", () => {
      state.focusedCardIndex = idx;
      syncFocusModeVisibility();
    });
    listEl.appendChild(item);

    const dot = document.createElement("span");
    dot.className = "focus-dot";
    dot.title = `${card.headword} — ${card.translation}`;
    dot.addEventListener("click", () => {
      state.focusedCardIndex = idx;
      syncFocusModeVisibility();
    });
    dotsEl.appendChild(dot);
  });
}

function syncFocusModeVisibility() {
  const total = state.cards.length;
  const counterBadge = document.getElementById("focus-counter-badge");
  if (counterBadge) {
    counterBadge.textContent = total ? `${state.focusedCardIndex + 1} / ${total}` : "0 / 0";
  }

  document.querySelectorAll(".focus-word-item").forEach((el, idx) => {
    el.classList.toggle("active", idx === state.focusedCardIndex);
  });

  document.querySelectorAll(".focus-dot").forEach((el, idx) => {
    el.classList.toggle("active", idx === state.focusedCardIndex);
  });

  document.querySelectorAll(".word-card").forEach((cardEl, idx) => {
    if (state.uiTheme === "v2") {
      cardEl.classList.toggle("hidden-in-focus", idx !== state.focusedCardIndex);
    } else {
      cardEl.classList.remove("hidden-in-focus");
    }
  });
}

// Відмальовка карток слів та речень
function renderCards() {
  cardsGrid.innerHTML = "";
  if (!state.cards.length) {
    cardsGrid.innerHTML = `
      <div class="builder-header-card" style="grid-column: 1 / -1;">
        <h3>Карток за цим фільтром не знайдено</h3>
        <p>Спробуйте змінити категорію або перейдіть у вкладку «➕ Додати слова», щоб створити нові матеріали.</p>
      </div>`;
    return;
  }

  state.cards.forEach((card) => {
    const cardEl = document.createElement("article");
    cardEl.className = "word-card";
    cardEl.dataset.cardId = card.id;

    const packBadge =
      card.pack_type === "grammar_topic"
        ? `<span class="pack-type-badge">⚡ Підтема</span>`
        : `<span class="pack-type-badge">🗂 Словник</span>`;

    const headerHtml = `
      <div class="word-card-header">
        <div>
          <div class="card-category-crumb">
            <span>${escapeHtml(card.category)}</span>
            ${packBadge}
          </div>
          <h2 class="card-headword-title">${escapeHtml(card.headword)} — ${escapeHtml(card.translation)}</h2>
          ${
            card.forms_summary
              ? `<div class="card-forms-summary">${escapeHtml(card.forms_summary)}</div>`
              : ""
          }
        </div>
        <div class="card-header-actions">
          <button class="icon-btn btn-speak-headword" data-word="${escapeAttr(card.headword)}" title="Прослухати вимову слова">
            🔊 Слово
          </button>
          <button class="icon-btn btn-play-card-loop" data-card-id="${card.id}" title="Запустити фоновий аудіо-режим починаючи з цієї картки">
            ▶ Слухати
          </button>
        </div>
      </div>
    `;

    const sentencesContainer = document.createElement("div");
    sentencesContainer.className = "card-sentences-list";

    (card.sentences || []).forEach((sent) => {
      const sentEl = createSentenceBlock(card, sent);
      sentencesContainer.appendChild(sentEl);
    });

    cardEl.innerHTML = headerHtml;
    cardEl.appendChild(sentencesContainer);

    cardEl.querySelector(".btn-speak-headword").addEventListener("click", () => {
      playSingleTTS(card.headword, "de", false);
    });

    cardEl.querySelector(".btn-play-card-loop").addEventListener("click", () => {
      startPodcastFromCard(card.id);
    });

    cardsGrid.appendChild(cardEl);
  });
}

function createSentenceBlock(card, sent) {
  const block = document.createElement("div");
  block.className = "sentence-block";
  block.id = `sentence-block-${sent.id}`;
  block.dataset.sentenceId = sent.id;
  block.dataset.level = sent.level || "просте";

  const tagsHtml = (sent.grammar_tags || [])
    .map((t) => `<span class="grammar-tag-pill">${escapeHtml(t)}</span>`)
    .join("");

  const notesListHtml = (sent.complexity_notes || [])
    .map((n) => `<li>${escapeHtml(n)}</li>`)
    .join("");

  block.innerHTML = `
    <div class="sentence-top-row">
      <div class="sentence-badges">
        <span class="level-pill">${escapeHtml(sent.level)}</span>
        ${tagsHtml}
      </div>
      <div class="sentence-audio-btns">
        <button class="audio-chip btn-sent-normal" title="Прослухати у нормальному темпі (1.0x)">
          ▶ DE
        </button>
        <button class="audio-chip btn-sent-slow" title="Прослухати повільно і чітко (0.8x)">
          🐢 0.8x
        </button>
        <button class="audio-chip btn-sent-uk" title="Прослухати український переклад">
          🇺🇦 UKR
        </button>
      </div>
    </div>
    <div class="sentence-de"></div>
    <div class="sentence-uk">${escapeHtml(sent.uk)}</div>
    <details class="complexity-details" ${state.expandAllNotes ? "open" : ""}>
      <summary class="complexity-summary">
        <span class="complexity-arrow">▶</span>
        <span>Чому така складність і що помітити</span>
      </summary>
      <div class="complexity-body">
        <ul class="complexity-list">${notesListHtml}</ul>
      </div>
    </details>
    <div class="sentence-source">${escapeHtml(sent.source || "Створено для навчання")}</div>
  `;

  const deContainer = block.querySelector(".sentence-de");
  renderInteractiveSentence(deContainer, sent.de, sent.tokens || []);

  block.querySelector(".btn-sent-normal").addEventListener("click", () => {
    playSentenceAudio(sent, "de_normal");
  });
  block.querySelector(".btn-sent-slow").addEventListener("click", () => {
    playSentenceAudio(sent, "de_slow");
  });
  block.querySelector(".btn-sent-uk").addEventListener("click", () => {
    playSentenceAudio(sent, "uk");
  });

  return block;
}

/**
 * Розбиває німецьке речення на слова і підключає інтерактивні токени з пунктирним підкресленням,
 * рамкою речення (Satzklammer) та спливаючим попапом.
 */
function renderInteractiveSentence(container, deText, tokens) {
  const parts = deText.split(/([A-Za-zÄÖÜäöüß]+)/g);
  const usedTokenIndices = new Set();

  parts.forEach((part) => {
    if (!part) return;
    const isWord = /^[A-Za-zÄÖÜäöüß]+$/.test(part);
    if (!isWord) {
      container.appendChild(document.createTextNode(part));
      return;
    }

    const tokenIdx = tokens.findIndex(
      (t, idx) => !usedTokenIndices.has(idx) && t.word === part
    );

    if (tokenIdx === -1) {
      container.appendChild(document.createTextNode(part));
      return;
    }

    usedTokenIndices.add(tokenIdx);
    const tokenData = tokens[tokenIdx];

    const span = document.createElement("span");
    span.className = `word-token pos-${tokenData.pos || "verb"}`;
    span.textContent = part;
    if (tokenData.frame_id) {
      span.dataset.frameId = tokenData.frame_id;
    }

    span.addEventListener("mouseenter", () => {
      clearTimeout(popupHideTimeout);
      highlightSatzklammer(container, tokenData.frame_id, span, true);
      showWordPopup(span, tokenData);
    });

    span.addEventListener("mouseleave", () => {
      highlightSatzklammer(container, tokenData.frame_id, span, false);
      scheduleHidePopup();
    });

    span.addEventListener("click", (e) => {
      e.stopPropagation();
      clearTimeout(popupHideTimeout);
      showWordPopup(span, tokenData);
    });

    container.appendChild(span);
  });
}

function highlightSatzklammer(sentenceContainer, frameId, hoveredEl, isActive) {
  if (!state.showSatzklammer || !frameId) return;
  sentenceContainer.querySelectorAll(".word-token").forEach((el) => {
    if (el !== hoveredEl && el.dataset.frameId === frameId) {
      el.classList.toggle("frame-partner-active", isActive);
    }
  });
}

function formatVowelShift(str) {
  if (!str) return "";
  const escaped = escapeHtml(str);
  return escaped.replace(/\[([^\]]+)\]/g, '<span class="vowel-shift">$1</span>');
}

function showWordPopup(targetEl, tokenData) {
  document.querySelectorAll(".word-token.active-token").forEach((el) => {
    el.classList.remove("active-token");
  });
  targetEl.classList.add("active-token");

  const p = tokenData.popup || {};
  let innerHtml = "";

  if (p.type === "verb") {
    const constructionsHtml =
      p.constructions && p.constructions.length
        ? `
          <div class="popup-divider"></div>
          <div class="popup-section-title">Конструкції та значення</div>
          <ul class="popup-constructions">
            ${p.constructions
              .map(
                (c) => `
              <li>
                <div class="constr-pattern">${escapeHtml(c.pattern)}</div>
                <div class="constr-meaning">${escapeHtml(c.meaning)}</div>
              </li>`
              )
              .join("")}
          </ul>
          <div style="font-size:11.5px; opacity:0.75; margin-top:6px;">
            Основні вживання для цієї проби; перелік не вичерпний.
          </div>
        `
        : "";

    const footerSummaryHtml = p.footer_summary
      ? `<div class="popup-divider"></div><div class="popup-note">${escapeHtml(p.footer_summary)}</div>`
      : "";

    innerHtml = `
      <div class="popup-grid">
        <div class="popup-row">
          <span class="popup-label">Інфінітив</span>
          <span class="popup-val">${escapeHtml(p.infinitive || tokenData.word)}</span>
        </div>
        <div class="popup-row">
          <span class="popup-label">Präsens · ти</span>
          <span class="popup-val">${formatVowelShift(p.praesens || "")}</span>
        </div>
        <div class="popup-row">
          <span class="popup-label">Präteritum · ти</span>
          <span class="popup-val">${escapeHtml(p.praeteritum || "")}</span>
        </div>
        <div class="popup-row">
          <span class="popup-label">Perfekt · er/sie/es</span>
          <span class="popup-val">${escapeHtml(p.perfekt || "")}</span>
        </div>
      </div>
      ${p.note ? `<div class="popup-divider"></div><div class="popup-note">${escapeHtml(p.note)}</div>` : ""}
      ${constructionsHtml}
      ${footerSummaryHtml}
      ${
        tokenData.context_role
          ? `<div class="popup-context-box">📍 <strong>У цьому реченні:</strong> ${escapeHtml(tokenData.context_role)}</div>`
          : ""
      }
      <div class="popup-footer-bar">
        <span style="font-size:11.5px; opacity:0.75;">Дієслово</span>
        <button class="popup-speak-btn" data-speak="${escapeAttr(p.infinitive || tokenData.word)}">
          🔊 Прослухати
        </button>
      </div>
    `;
  } else if (p.type === "noun") {
    innerHtml = `
      <div class="popup-grid">
        <div class="popup-row">
          <span class="popup-label">Однина · Nominativ</span>
          <span class="popup-val">${escapeHtml(p.singular_nom || tokenData.word)}</span>
        </div>
        <div class="popup-row">
          <span class="popup-label">Множина · Nominativ</span>
          <span class="popup-val">${escapeHtml(p.plural_nom || "—")}</span>
        </div>
      </div>
      ${
        tokenData.context_role
          ? `<div class="popup-context-box">📍 <strong>У цьому реченні:</strong> ${escapeHtml(tokenData.context_role)}</div>`
          : ""
      }
      <div class="popup-footer-bar">
        <span style="font-size:11.5px; opacity:0.75;">Іменник</span>
        <button class="popup-speak-btn" data-speak="${escapeAttr(p.singular_nom || tokenData.word)}">
          🔊 Прослухати
        </button>
      </div>
    `;
  } else {
    innerHtml = `
      <div class="popup-section-title">${escapeHtml(p.title || tokenData.word)}</div>
      <div class="popup-note">${escapeHtml(p.explanation || "")}</div>
      ${
        tokenData.context_role
          ? `<div class="popup-context-box">📍 <strong>Роль:</strong> ${escapeHtml(tokenData.context_role)}</div>`
          : ""
      }
      <div class="popup-footer-bar">
        <span style="font-size:11.5px; opacity:0.75;">Синтаксис / Керування</span>
        <button class="popup-speak-btn" data-speak="${escapeAttr(tokenData.word)}">
          🔊 Прослухати
        </button>
      </div>
    `;
  }

  wordPopup.innerHTML = innerHtml;
  wordPopup.classList.remove("hidden");

  const speakBtn = wordPopup.querySelector(".popup-speak-btn");
  if (speakBtn) {
    speakBtn.addEventListener("click", () => {
      playSingleTTS(speakBtn.dataset.speak, "de", false);
    });
  }

  positionPopup(targetEl);
}

function positionPopup(targetEl) {
  const rect = targetEl.getBoundingClientRect();
  const popupRect = wordPopup.getBoundingClientRect();
  const margin = 10;

  let top = rect.bottom + margin;
  if (top + popupRect.height > window.innerHeight - 90 && rect.top - popupRect.height - margin > 12) {
    top = rect.top - popupRect.height - margin;
  }

  let left = rect.left;
  if (left + popupRect.width > window.innerWidth - 16) {
    left = window.innerWidth - popupRect.width - 16;
  }
  if (left < 12) left = 12;

  wordPopup.style.top = `${Math.max(12, top)}px`;
  wordPopup.style.left = `${left}px`;
}

function scheduleHidePopup() {
  clearTimeout(popupHideTimeout);
  popupHideTimeout = setTimeout(() => {
    hidePopupImmediate();
  }, 220);
}

function hidePopupImmediate() {
  wordPopup.classList.add("hidden");
  document.querySelectorAll(".word-token.active-token").forEach((el) => {
    el.classList.remove("active-token");
  });
}

// ==================== АУДІО ТА ФОНОВИЙ РЕЖИМ ПОДКАСТУ ====================

function getGlobalAudioElement() {
  let el = document.getElementById("global-audio-player");
  if (!el) {
    el = document.createElement("audio");
    el.id = "global-audio-player";
    el.preload = "auto";
    document.body.appendChild(el);
  }
  return el;
}

function stopCurrentAudio() {
  const audio = getGlobalAudioElement();
  audio.onended = null;
  audio.onerror = null;
  try {
    audio.pause();
  } catch (_) {}

  if (state.currentAudioResolve) {
    const r = state.currentAudioResolve;
    state.currentAudioResolve = null;
    r();
  }

  if ("speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
    } catch (_) {}
  }
}

async function playAudioUrl(url, fallbackText = "", fallbackLang = "de-DE", slow = false) {
  stopCurrentAudio();
  if (url) {
    return new Promise((resolve) => {
      state.currentAudioResolve = resolve;
      const audio = getGlobalAudioElement();
      state.currentAudio = audio;

      const finish = () => {
        if (state.currentAudioResolve === resolve) {
          state.currentAudioResolve = null;
        }
        audio.onended = null;
        audio.onerror = null;
        resolve();
      };

      audio.onended = finish;
      audio.onerror = () => {
        audio.onended = null;
        audio.onerror = null;
        fallbackBrowserTTS(fallbackText, fallbackLang, slow).then(finish);
      };

      audio.src = url;
      audio.playbackRate = 1.0;
      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.catch((err) => {
          console.warn("Audio play fallback:", err);
          fallbackBrowserTTS(fallbackText, fallbackLang, slow).then(finish);
        });
      }
    });
  }
  return fallbackBrowserTTS(fallbackText, fallbackLang, slow);
}

function fallbackBrowserTTS(text, lang = "de-DE", slow = false) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window) || !text) {
      resolve();
      return;
    }
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = lang;
    utter.rate = slow ? 0.78 : 1.0;
    utter.onend = () => resolve();
    utter.onerror = () => resolve();
    window.speechSynthesis.speak(utter);
  });
}

async function playSingleTTS(text, lang = "de", slow = false) {
  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, lang, slow }),
    });
    const data = await res.json();
    if (data.ok && data.url) {
      await playAudioUrl(data.url, text, lang === "de" ? "de-DE" : "uk-UA", slow);
      return;
    }
  } catch (_) {}
  await fallbackBrowserTTS(text, lang === "de" ? "de-DE" : "uk-UA", slow);
}

async function playSentenceAudio(sent, kind = "de_normal") {
  if (kind === "de_normal") {
    if (sent.audio_de_normal) {
      await playAudioUrl(sent.audio_de_normal, sent.de, "de-DE", false);
    } else {
      await playSingleTTS(sent.de, "de", false);
    }
  } else if (kind === "de_slow") {
    if (sent.audio_de_slow) {
      await playAudioUrl(sent.audio_de_slow, sent.de, "de-DE", true);
    } else {
      await playSingleTTS(sent.de, "de", true);
    }
  } else if (kind === "uk") {
    if (sent.audio_uk) {
      await playAudioUrl(sent.audio_uk, sent.uk, "uk-UA", false);
    } else {
      await playSingleTTS(sent.uk, "uk", false);
    }
  }
}

function rebuildPlaylist(forceShuffle = null) {
  const pattern = document.getElementById("audio-pattern-select")?.value || "random_word_3";
  const shouldShuffle = forceShuffle !== null ? forceShuffle : pattern === "random_word_3";

  // Створюємо масив пар (card, originalIndex)
  const indexedCards = state.cards.map((card, idx) => ({ card, originalIdx: idx }));

  if (shouldShuffle && indexedCards.length > 1) {
    // Перемішуємо САМІ СЛОВА (картки) за алгоритмом Фішера-Єйтса,
    // але всі 3 речення одного слова залишаються разом підряд!
    for (let i = indexedCards.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [indexedCards[i], indexedCards[j]] = [indexedCards[j], indexedCards[i]];
    }
  }

  const list = [];
  indexedCards.forEach(({ card, originalIdx }, wordOrderIdx) => {
    const sents = card.sentences || [];
    sents.forEach((sent, sIdx) => {
      list.push({
        cardId: card.id,
        cardIndex: originalIdx,
        wordOrderNumber: wordOrderIdx + 1,
        totalWords: indexedCards.length,
        sentInCardNumber: sIdx + 1,
        totalSentsInCard: sents.length,
        headword: card.headword,
        translation: card.translation,
        category: card.category,
        sentence: sent,
      });
    });
  });

  state.playlist = list;
  if (state.currentTrackIndex >= list.length) {
    state.currentTrackIndex = 0;
  }

  if (!state.isPlayingPodcast && list.length > 0) {
    document.getElementById("player-phase-badge").textContent =
      `Готово: ${indexedCards.length} слів (${list.length} речень)`;
  }
}

function startPodcastFromCard(cardId) {
  let idx = state.playlist.findIndex((item) => item.cardId === cardId);
  if (idx === -1) {
    rebuildPlaylist(false);
    idx = state.playlist.findIndex((item) => item.cardId === cardId);
  }
  if (idx !== -1) {
    state.currentTrackIndex = idx;
  }
  restartPodcastLoopFromCurrent();
}

function togglePodcastPlayback() {
  if (!state.playlist.length && state.cards.length) {
    rebuildPlaylist();
  }
  if (!state.playlist.length) return;

  if (state.isPlayingPodcast) {
    stopPodcastPlayback();
  } else {
    const pattern = document.getElementById("audio-pattern-select")?.value || "random_word_3";
    if (pattern === "random_word_3" && state.currentTrackIndex === 0) {
      rebuildPlaylist(true);
    }
    startPodcastPlayback();
  }
}

function stopPodcastPlayback() {
  state.isPlayingPodcast = false;
  if (state.podcastAbortController) {
    state.podcastAbortController.abort();
    state.podcastAbortController = null;
  }
  stopCurrentAudio();
  document.getElementById("btn-play-pause").textContent = "▶";
  document.getElementById("player-phase-badge").textContent = "На паузі";
  document.querySelectorAll(".sentence-block.playing-active").forEach((el) => {
    el.classList.remove("playing-active");
  });
}

function skipPodcastTrack(delta) {
  if (!state.playlist.length) return;
  state.currentTrackIndex =
    (state.currentTrackIndex + delta + state.playlist.length) % state.playlist.length;
  if (state.isPlayingPodcast) {
    restartPodcastLoopFromCurrent();
  } else {
    updateDockDisplay(state.playlist[state.currentTrackIndex], "Вибрано речення");
  }
}

function restartPodcastLoopFromCurrent() {
  state.isPlayingPodcast = false;
  if (state.podcastAbortController) {
    state.podcastAbortController.abort();
    state.podcastAbortController = null;
  }
  stopCurrentAudio();
  startPodcastPlayback();
}

function waitAbortable(ms, signal) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(t);
        reject(new Error("aborted"));
      },
      { once: true }
    );
  });
}

function updateDockDisplay(trackItem, phaseText) {
  if (
    typeof trackItem.cardIndex === "number" &&
    trackItem.cardIndex !== state.focusedCardIndex
  ) {
    state.focusedCardIndex = trackItem.cardIndex;
    syncFocusModeVisibility();
  }

  document.getElementById("player-phase-badge").textContent = phaseText;
  document.getElementById("player-card-tag").textContent = `${trackItem.headword} — ${trackItem.translation} (${trackItem.sentence.level})`;
  document.getElementById("player-de-text").textContent = trackItem.sentence.de;
  document.getElementById("player-uk-text").textContent = trackItem.sentence.uk;

  document.querySelectorAll(".sentence-block.playing-active").forEach((el) => {
    el.classList.remove("playing-active");
  });
  const blockEl = document.getElementById(`sentence-block-${trackItem.sentence.id}`);
  if (blockEl) {
    blockEl.classList.add("playing-active");
  }

  try {
    if ("mediaSession" in navigator && typeof MediaMetadata !== "undefined") {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: trackItem.sentence.de,
        artist: `${trackItem.headword} — ${trackItem.translation}`,
        album: trackItem.sentence.uk,
      });
      navigator.mediaSession.setActionHandler("play", () => startPodcastPlayback());
      navigator.mediaSession.setActionHandler("pause", () => stopPodcastPlayback());
      navigator.mediaSession.setActionHandler("previoustrack", () => skipPodcastTrack(-1));
      navigator.mediaSession.setActionHandler("nexttrack", () => skipPodcastTrack(1));
    }
  } catch (_) {}
}

async function startPodcastPlayback() {
  state.isPlayingPodcast = true;
  document.getElementById("btn-play-pause").textContent = "⏸";

  const controller = new AbortController();
  state.podcastAbortController = controller;
  const { signal } = controller;

  try {
    while (state.isPlayingPodcast && !signal.aborted) {
      const item = state.playlist[state.currentTrackIndex];
      if (!item) break;

      const pattern = document.getElementById("audio-pattern-select").value;
      const pauseSec = parseFloat(document.getElementById("pause-seconds-select").value || "1.5");
      const pauseMs = Math.round(pauseSec * 1000);

      if (pattern === "random_word_3") {
        const sentNum = item.sentInCardNumber || 1;
        const sentTotal = item.totalSentsInCard || 3;
        const wordNum = item.wordOrderNumber || 1;
        const wordTotal = item.totalWords || state.cards.length;

        updateDockDisplay(
          item,
          `🎲 Слово ${wordNum}/${wordTotal} · Речення ${sentNum}/${sentTotal} (${item.sentence.level})`
        );
        await playSentenceAudio(item.sentence, "de_normal");
        if (signal.aborted) break;

        // Коротка пауза між 3 реченнями одного слова, і трохи відчутніша перед новим словом
        if (sentNum < sentTotal) {
          updateDockDisplay(item, `⏳ Пауза між реченнями (${pauseSec} с)...`);
          await waitAbortable(pauseMs, signal);
        } else {
          updateDockDisplay(item, `🔀 Наступне випадкове слово через ${pauseSec} с...`);
          await waitAbortable(pauseMs + 600, signal);
        }
      } else if (pattern === "recall") {
        updateDockDisplay(item, "🇺🇦 1/4 · Слухаємо переклад");
        await playSentenceAudio(item.sentence, "uk");
        if (signal.aborted) break;

        const recallSecs = Math.max(1, Math.round(pauseSec));
        for (let s = recallSecs; s > 0; s--) {
          updateDockDisplay(item, `⏳ 2/4 · Згадайте німецькою (${s} с)...`);
          await waitAbortable(1000, signal);
        }

        updateDockDisplay(item, "🐢 3/4 · Німецька (повільно 0.8x)");
        await playSentenceAudio(item.sentence, "de_slow");
        if (signal.aborted) break;
        await waitAbortable(900, signal);

        updateDockDisplay(item, "🇩🇪 4/4 · Німецька (природно 1.0x)");
        await playSentenceAudio(item.sentence, "de_normal");
        if (signal.aborted) break;
        await waitAbortable(pauseMs, signal);
      } else if (pattern === "immersion") {
        updateDockDisplay(item, "🇩🇪 1/3 · Німецька (1.0x)");
        await playSentenceAudio(item.sentence, "de_normal");
        if (signal.aborted) break;
        await waitAbortable(700, signal);

        updateDockDisplay(item, "🇺🇦 2/3 · Український переклад");
        await playSentenceAudio(item.sentence, "uk");
        if (signal.aborted) break;
        await waitAbortable(700, signal);

        updateDockDisplay(item, "🇩🇪 3/3 · Закріплення (1.0x)");
        await playSentenceAudio(item.sentence, "de_normal");
        if (signal.aborted) break;
        await waitAbortable(pauseMs, signal);
      } else if (pattern === "de_only") {
        updateDockDisplay(item, "🐢 1/2 · Німецька (0.8x)");
        await playSentenceAudio(item.sentence, "de_slow");
        if (signal.aborted) break;
        await waitAbortable(pauseMs, signal);

        updateDockDisplay(item, "🇩🇪 2/2 · Німецька (1.0x)");
        await playSentenceAudio(item.sentence, "de_normal");
        if (signal.aborted) break;
        await waitAbortable(pauseMs, signal);
      } else {
        updateDockDisplay(item, "🇩🇪 Німецька (1.0x)");
        await playSentenceAudio(item.sentence, "de_normal");
        if (signal.aborted) break;
        await waitAbortable(pauseMs, signal);
      }

      if (signal.aborted) break;

      const loopEnabled = document.getElementById("player-loop").checked;
      if (state.currentTrackIndex + 1 < state.playlist.length) {
        state.currentTrackIndex += 1;
      } else if (loopEnabled) {
        // Коли пройшли всі слова по колу, у режимі рандому наново перемішуємо слова!
        if (pattern === "random_word_3") {
          rebuildPlaylist(true);
        }
        state.currentTrackIndex = 0;
      } else {
        stopPodcastPlayback();
        break;
      }
    }
  } catch (err) {
    if (err.message !== "aborted") {
      console.error("Podcast error:", err);
    }
  }
}

// ==================== AI КОНСТРУКТОР ТА ІМПОРТ JSON ====================

async function handleGeneratePrompt() {
  const mode = document.querySelector('input[name="gen-mode"]:checked')?.value || "word_list";
  const categoryName = document.getElementById("builder-category").value.trim() || "Нові слова";
  const userInput = document.getElementById("builder-words").value.trim();
  const includeKnown = document.getElementById("builder-include-vocab").checked;

  if (!userInput) {
    alert("Введіть список слів або оберіть шаблон граматичної підтеми!");
    return;
  }

  const res = await fetch("/api/build-prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode,
      category_name: categoryName,
      user_input: userInput,
      include_known_vocab: includeKnown,
    }),
  });
  const data = await res.json();
  const outputEl = document.getElementById("prompt-output");
  outputEl.value = data.prompt || "";
  document.getElementById("btn-copy-prompt").disabled = false;
}

async function handleCopyPrompt() {
  const outputEl = document.getElementById("prompt-output");
  if (!outputEl.value) return;
  await navigator.clipboard.writeText(outputEl.value);
  const btn = document.getElementById("btn-copy-prompt");
  const prev = btn.textContent;
  btn.textContent = "✅ Скопійовано!";
  setTimeout(() => {
    btn.textContent = prev;
  }, 1800);
}

async function handleImportJson() {
  const jsonText = document.getElementById("json-import-input").value.trim();
  const generateTts = document.getElementById("import-run-tts").checked;
  const statusBox = document.getElementById("import-status");

  if (!jsonText) {
    statusBox.textContent = "Будь ласка, вставте JSON-пакет у поле вище.";
    statusBox.className = "status-box error";
    statusBox.classList.remove("hidden");
    return;
  }

  statusBox.textContent = "⏳ Імпортуємо картки у SQLite та синтезуємо озвучку Edge-TTS...";
  statusBox.className = "status-box";
  statusBox.classList.remove("hidden");

  try {
    const res = await fetch("/api/import-pack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ json_text: jsonText, generate_tts: generateTts }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Помилка імпорту");
    }

    statusBox.innerHTML = `
      ✅ <strong>Успішно імпортовано!</strong> Додано карток: <b>${data.import.imported_cards}</b>,
      речень: <b>${data.import.imported_sentences}</b>.
      Озвучено нових речень: <b>${data.tts.generated}</b>.
      Перейдіть на вкладку «Усі», щоб почати навчання!
    `;
    await loadCards();
  } catch (err) {
    statusBox.textContent = `❌ ${err.message}`;
    statusBox.className = "status-box error";
  }
}

async function handleRegenerateAllTTS() {
  const statusBox = document.getElementById("import-status");
  statusBox.textContent = "🔊 Перевіряємо та генеруємо MP3 озвучку для всіх речень у базі...";
  statusBox.className = "status-box";
  statusBox.classList.remove("hidden");

  try {
    const res = await fetch("/api/generate-audio", { method: "POST" });
    const data = await res.json();
    statusBox.innerHTML = `✅ Озвучку оновлено! Згенеровано нових комплектів аудіо: <b>${data.stats.generated}</b>.`;
    await loadCards();
  } catch (err) {
    statusBox.textContent = `❌ Помилка генерації озвучки: ${err.message}`;
    statusBox.className = "status-box error";
  }
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/'/g, "&#39;");
}
