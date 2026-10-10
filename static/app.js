document.addEventListener("DOMContentLoaded", () => {
  // --- Tab Navigation ---
  const navTabs = document.querySelectorAll(".nav-tab");
  const tabContents = document.querySelectorAll(".tab-content");

  navTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      navTabs.forEach((t) => t.classList.remove("active"));
      tabContents.forEach((c) => c.classList.remove("active"));

      tab.classList.add("active");
      const targetId = tab.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");

      if (targetId === "tab-library") {
        loadLibrary();
      } else if (targetId === "tab-lab") {
        loadDiagnosticsTable();
      } else if (targetId === "tab-settings") {
        loadSettings();
      }
    });
  });

  // --- Library Update Button ---
  const btnUpdateLibrary = document.getElementById("btn-update-library");
  if (btnUpdateLibrary) {
    btnUpdateLibrary.addEventListener("click", async () => {
      btnUpdateLibrary.textContent = "Checking...";
      btnUpdateLibrary.disabled = true;
      try {
        const res = await fetch("/api/library/update", { method: "POST" });
        const data = await res.json();
        if (data.success) {
          alert("Library update started in background! Monitor progress on the Downloader tab.");
        } else {
          alert("Error: " + data.error);
        }
      } catch (e) {
        alert("Network error: " + e.message);
      } finally {
        btnUpdateLibrary.textContent = "🔄 Check Updates";
        btnUpdateLibrary.disabled = false;
      }
    });
  }

  // --- Download Options Visibility ---
  const downloadModeSelect = document.getElementById("download-mode");
  const countField = document.getElementById("count-field");

  downloadModeSelect.addEventListener("change", () => {
    if (downloadModeSelect.value === "range") {
      countField.style.display = "block";
    } else {
      countField.style.display = "none";
    }
  });

  // --- Series Chapter Catalog Inspector ---
  let currentCatalogChapters = [];
  let currentCatalogUrl = "";
  let currentSeriesTitle = "";

  const chapterUrlInput = document.getElementById("chapter-url");
  const btnInspect = document.getElementById("btn-inspect");
  const btnAnalyze = document.getElementById("btn-analyze");
  const previewCard = document.getElementById("analyze-preview");
  const seriesCatalogCard = document.getElementById("series-catalog-card");
  const catFilterInput = document.getElementById("cat-filter-input");
  const btnSelectAll = document.getElementById("btn-select-all");
  const btnDeselectAll = document.getElementById("btn-deselect-all");
  const btnDownloadSelected = document.getElementById("btn-download-selected");
  const catSelectedCount = document.getElementById("cat-selected-count");

  async function inspectSeries(url, isSilent = false) {
    if (!url) {
      if (!isSilent) alert("Please enter a valid manga or chapter URL.");
      return;
    }

    if (!isSilent && btnInspect) {
      btnInspect.textContent = "🔍 Browsing...";
      btnInspect.disabled = true;
    }

    try {
      const res = await fetch("/api/inspect-series", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await res.json();

      if (data.success) {
        currentCatalogChapters = data.chapters || [];
        currentCatalogUrl = url;
        currentSeriesTitle = data.series_title || "Unknown Series";

        // Populate catalog card header
        const coverImg = document.getElementById("cat-series-cover");
        if (coverImg) {
          if (data.cover_url) {
            coverImg.src = data.cover_url;
            coverImg.style.display = "block";
          } else {
            coverImg.src = 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="80" height="110"><rect fill="%231c2640" width="80" height="110"/><text fill="%2394a3b8" x="50%" y="50%" text-anchor="middle" font-size="10">No Cover</text></svg>';
          }
        }
        const badgeElem = document.getElementById("cat-engine-badge");
        if (badgeElem) badgeElem.textContent = `Engine: ${data.engine_name || 'Auto'}`;

        const titleElem = document.getElementById("cat-series-title");
        if (titleElem) titleElem.textContent = data.series_title || "Discovered Series";

        const statsElem = document.getElementById("cat-stats");
        if (statsElem) {
          statsElem.textContent = `📊 ${data.total_chapters} chapters found (${data.downloaded_count} downloaded)`;
        }

        const synElem = document.getElementById("cat-synopsis");
        if (synElem) {
          synElem.textContent = data.synopsis || "Select chapters below to download or read.";
        }

        renderCatalogChapters(catFilterInput ? catFilterInput.value.trim() : "");
        if (seriesCatalogCard) {
          seriesCatalogCard.classList.remove("hidden");
          if (!isSilent) {
            seriesCatalogCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
          }
        }
      } else {
        if (!isSilent) alert(`Failed to inspect catalog: ${data.error || 'Unknown error'}`);
      }
    } catch (err) {
      if (!isSilent) alert(`Network error inspecting series: ${err.message}`);
    } finally {
      if (!isSilent && btnInspect) {
        btnInspect.textContent = "🔍 Browse Chapters";
        btnInspect.disabled = false;
      }
    }
  }

  function renderCatalogChapters(filterText = "") {
    const listContainer = document.getElementById("catalog-chapters-list");
    if (!listContainer) return;

    const filter = (filterText || "").toLowerCase();
    const filtered = currentCatalogChapters.filter(ch => {
      const titleStr = (ch.title || `Chapter ${ch.chapter_num}`).toLowerCase();
      const numStr = String(ch.chapter_num);
      return !filter || titleStr.includes(filter) || numStr.includes(filter);
    });

    if (filtered.length === 0) {
      listContainer.innerHTML = '<p style="padding: 1rem; color: var(--text-muted); text-align: center;">No matching chapters found.</p>';
      updateCatalogSelectedCount();
      return;
    }

    listContainer.innerHTML = filtered.map(ch => {
      const chTitle = ch.title || `Chapter ${ch.chapter_num}`;
      const isSaved = ch.is_downloaded;
      const encodedUrl = encodeURIComponent(ch.url);
      return `
        <div class="catalog-chapter-row" data-url="${ch.url}">
          <div class="catalog-chapter-left">
            <input type="checkbox" class="cat-ch-checkbox" data-url="${ch.url}" style="width: 18px; height: 18px; cursor: pointer; accent-color: var(--accent);">
            <div style="cursor: pointer;" onclick="toggleCatalogCheckbox('${ch.url}')">
              <strong style="font-size: 0.95rem; color: var(--text-main);">${chTitle}</strong>
              ${ch.read_status === 1 ? '<span style="margin-left: 6px; font-size: 0.75rem; color: #a78bfa;">✓ Read</span>' : ''}
            </div>
          </div>
          <div class="catalog-chapter-right">
            ${isSaved 
              ? `<span class="badge-local">🟢 Saved</span>
                 <button class="btn-read-now" onclick="openReader(${ch.chapter_id})">📖 Read Now</button>
                 <a href="/api/download/file/${ch.chapter_id}" class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.75rem; text-decoration: none;" download title="Save ${ch.file_format || 'CBZ'}">💾</a>`
              : `<span class="badge-online">⚪ Online</span>
                 <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.8rem;" onclick="window.downloadSingleCatalogChapter('${encodedUrl}')">⬇️ Download</button>`
            }
          </div>
        </div>
      `;
    }).join("");

    const checkboxes = listContainer.querySelectorAll(".cat-ch-checkbox");
    checkboxes.forEach(cb => {
      cb.addEventListener("change", updateCatalogSelectedCount);
    });
    updateCatalogSelectedCount();
  }

  window.toggleCatalogCheckbox = function(url) {
    const cb = document.querySelector(`.cat-ch-checkbox[data-url="${url}"]`);
    if (cb) {
      cb.checked = !cb.checked;
      updateCatalogSelectedCount();
    }
  };

  function updateCatalogSelectedCount() {
    const selected = document.querySelectorAll(".cat-ch-checkbox:checked");
    if (catSelectedCount) {
      catSelectedCount.textContent = selected.length;
    }
  }

  if (btnInspect) {
    btnInspect.addEventListener("click", () => {
      const url = chapterUrlInput.value.trim();
      inspectSeries(url);
    });
  }

  if (chapterUrlInput) {
    chapterUrlInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        btnInspect.click();
      }
    });
  }

  if (catFilterInput) {
    catFilterInput.addEventListener("input", () => {
      renderCatalogChapters(catFilterInput.value.trim());
    });
  }

  if (btnSelectAll) {
    btnSelectAll.addEventListener("click", () => {
      const checkboxes = document.querySelectorAll(".cat-ch-checkbox");
      checkboxes.forEach(cb => cb.checked = true);
      updateCatalogSelectedCount();
    });
  }

  if (btnDeselectAll) {
    btnDeselectAll.addEventListener("click", () => {
      const checkboxes = document.querySelectorAll(".cat-ch-checkbox");
      checkboxes.forEach(cb => cb.checked = false);
      updateCatalogSelectedCount();
    });
  }

  if (btnDownloadSelected) {
    btnDownloadSelected.addEventListener("click", () => {
      const selected = document.querySelectorAll(".cat-ch-checkbox:checked");
      const urls = Array.from(selected).map(cb => cb.getAttribute("data-url")).filter(Boolean);
      startCatalogDownload(urls);
    });
  }

  window.downloadSingleCatalogChapter = function(encodedUrl) {
    const url = decodeURIComponent(encodedUrl);
    startCatalogDownload([url]);
  };

  async function startCatalogDownload(urls) {
    if (!urls || urls.length === 0) {
      alert("Please select at least one chapter to download.");
      return;
    }

    const format = document.getElementById("output-format").value;
    const maxWidth = parseInt(document.getElementById("max-width").value) || 1080;
    const sliceEink = document.getElementById("slice-eink").checked;
    const imageFormat = document.getElementById("image-encoding") ? document.getElementById("image-encoding").value : "webp";
    const upscaleScale = document.getElementById("upscale-factor") ? parseInt(document.getElementById("upscale-factor").value, 10) : 1;
    const filterPromosElem = document.getElementById("filter-promos");
    const filterPromos = filterPromosElem ? filterPromosElem.checked : true;

    if (btnStartDownload) btnStartDownload.disabled = true;
    if (btnDownloadSelected) btnDownloadSelected.disabled = true;

    try {
      const res = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: urls[0],
          chapter_urls: urls,
          mode: "range",
          count: urls.length,
          format: format,
          max_width: maxWidth,
          image_format: imageFormat,
          upscale_scale: upscaleScale,
          slice_eink: sliceEink,
          filter_promos: filterPromos
        })
      });

      const data = await res.json();
      if (data.success) {
        progressCard.classList.remove("hidden");
        progressCard.scrollIntoView({ behavior: "smooth" });
        listenToProgress();
      } else {
        alert(`Error starting download: ${data.error}`);
        if (btnStartDownload) btnStartDownload.disabled = false;
        if (btnDownloadSelected) btnDownloadSelected.disabled = false;
      }
    } catch (err) {
      alert(`Failed to launch download: ${err.message}`);
      if (btnStartDownload) btnStartDownload.disabled = false;
      if (btnDownloadSelected) btnDownloadSelected.disabled = false;
    }
  }

  // --- Analyze URL ---
  btnAnalyze.addEventListener("click", async () => {
    const url = chapterUrlInput.value.trim();
    if (!url) {
      alert("Please enter a valid chapter URL.");
      return;
    }

    btnAnalyze.textContent = "Analyzing...";
    btnAnalyze.disabled = true;

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await res.json();

      if (data.success) {
        document.getElementById("preview-engine-badge").textContent = `Engine: ${data.engine_name}`;
        document.getElementById("preview-title").textContent = data.series_title || "Unknown Series";
        document.getElementById("preview-ch").textContent = data.chapter_num || "1";
        document.getElementById("preview-panels").textContent = data.panel_count || "0";

        const nextElem = document.getElementById("preview-next-text");
        if (data.next_chapter_url) {
          nextElem.textContent = "✅ Next chapter link detected in navigation!";
        } else {
          nextElem.textContent = "ℹ️ Will use smart template incrementation for subsequent chapters.";
        }
        previewCard.classList.remove("hidden");
      } else {
        alert(`Analysis failed: ${data.error || "Could not isolate chapter layout."}`);
      }
    } catch (err) {
      alert(`Network error during analysis: ${err.message}`);
    } finally {
      btnAnalyze.textContent = "Analyze";
      btnAnalyze.disabled = false;
    }
  });

  // --- Start Download ---
  const btnStartDownload = document.getElementById("btn-start-download");
  const progressCard = document.getElementById("progress-card");

  btnStartDownload.addEventListener("click", async () => {
    const url = chapterUrlInput.value.trim();
    if (!url) {
      alert("Please enter a chapter URL first.");
      return;
    }

    const mode = downloadModeSelect.value;
    const count = parseInt(document.getElementById("chapter-count").value) || 1;
    const format = document.getElementById("output-format").value;
    const maxWidth = parseInt(document.getElementById("max-width").value) || 1080;
    const sliceEink = document.getElementById("slice-eink").checked;
    const imageFormat = document.getElementById("image-encoding") ? document.getElementById("image-encoding").value : "webp";
    const upscaleScale = document.getElementById("upscale-factor") ? parseInt(document.getElementById("upscale-factor").value, 10) : 1;
    const filterPromosElem = document.getElementById("filter-promos");
    const filterPromos = filterPromosElem ? filterPromosElem.checked : true;

    btnStartDownload.disabled = true;

    try {
      const res = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          mode,
          count,
          format,
          max_width: maxWidth,
          image_format: imageFormat,
          upscale_scale: upscaleScale,
          slice_eink: sliceEink,
          filter_promos: filterPromos
        })
      });

      const data = await res.json();
      if (data.success) {
        progressCard.classList.remove("hidden");
        listenToProgress();
      } else {
        alert(`Error: ${data.error}`);
        btnStartDownload.disabled = false;
      }
    } catch (err) {
      alert(`Failed to launch download: ${err.message}`);
      btnStartDownload.disabled = false;
    }
  });

  // --- Live Progress SSE Stream ---
  let eventSource = null;

  function listenToProgress() {
    if (eventSource) {
      eventSource.close();
    }

    eventSource = new EventSource("/api/download/progress");

    eventSource.onmessage = (event) => {
      try {
        const state = JSON.parse(event.data);

        document.getElementById("prog-series-title").textContent = state.series_title || "Downloading Series";
        document.getElementById("prog-status-text").textContent = state.status.toUpperCase();
        document.getElementById("prog-message").textContent = state.message;
        document.getElementById("prog-chapter-tracker").textContent = `Chapter ${state.chapter_index} of ${state.total_chapters}`;

        if (state.total_panels > 0) {
          const pct = Math.round((state.current_panel / state.total_panels) * 100);
          document.getElementById("progress-bar-fill").style.width = `${pct}%`;
          document.getElementById("prog-panel-count").textContent = `${state.current_panel} / ${state.total_panels} panels`;
        }

        if (!state.is_running && (state.status === "completed" || state.status === "error")) {
          btnStartDownload.disabled = false;
          if (btnDownloadSelected) btnDownloadSelected.disabled = false;
          if (state.status === "completed") {
            loadLibrary(); // update library count
            if (currentCatalogUrl) {
              inspectSeries(currentCatalogUrl, true); // silent refresh updates local badges & read now buttons!
            }
          }
        }
      } catch (e) {
        console.error("SSE parse error", e);
      }
    };

    eventSource.onerror = () => {
      // EventSource reconnects automatically
    };
  }

  // --- Library Tab ---
  async function loadLibrary() {
    const grid = document.getElementById("library-grid");
    try {
      const res = await fetch("/api/library");
      const data = await res.json();

      if (data.success && data.series && data.series.length > 0) {
        document.getElementById("library-count").textContent = data.series.length;
        grid.innerHTML = data.series.map((s) => `
          <div class="series-card" onclick="openSeriesModal(${s.id})" style="cursor: pointer;">
            <img class="series-cover" src="${s.cover_url || '/static/placeholder.jpg'}" alt="${s.title}" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'200\\' height=\\'250\\'><rect fill=\\'%231c2640\\' width=\\'200\\' height=\\'250\\'/><text fill=\\'%2394a3b8\\' x=\\'50%\\' y=\\'50%\\' text-anchor=\\'middle\\'>No Cover</text></svg>'">
            <div class="series-details">
              <h4 class="series-title">${s.title}</h4>
              <p class="series-meta">
                📥 <strong>${s.downloaded_chapters || 0}</strong> chapters downloaded<br>
                Engine: ${s.engine || 'Auto'}
              </p>
            </div>
          </div>
        `).join("");
      } else {
        document.getElementById("library-count").textContent = "0";
        grid.innerHTML = '<p class="empty-state">No downloaded series in the database yet. Download a chapter to start building your library!</p>';
      }
    } catch (err) {
      grid.innerHTML = `<p class="empty-state">Error loading library: ${err.message}</p>`;
    }
  }

  // --- Series Details Modal ---
  const seriesModal = document.getElementById("series-modal");
  const modalClose = document.getElementById("modal-close");

  modalClose.addEventListener("click", () => {
    seriesModal.classList.add("hidden");
  });

  window.openSeriesModal = async function(seriesId) {
    try {
      const res = await fetch(`/api/library/${seriesId}`);
      const data = await res.json();
      if (data.success && data.series) {
        const s = data.series;
        document.getElementById("modal-series-title").textContent = s.title;
        document.getElementById("modal-series-cover").src = s.cover_url || "";
        document.getElementById("modal-engine-badge").textContent = `Engine: ${s.engine || 'Auto'}`;
        document.getElementById("modal-synopsis").textContent = s.synopsis || "Tracked in local library database.";

        const metaParts = [];
        if (s.author) metaParts.push(`✍️ <strong>${s.author}</strong>`);
        if (s.artist) metaParts.push(`🎨 <strong>${s.artist}</strong>`);
        if (s.genres) metaParts.push(`🏷️ ${s.genres}`);
        if (s.year) metaParts.push(`📅 ${s.year}`);
        document.getElementById("modal-meta-tags").innerHTML = metaParts.length > 0 ? metaParts.join(" &bull; ") : "<em>No author/genre metadata cached yet.</em>";

        const btnRefreshMeta = document.getElementById("modal-btn-refresh-meta");
        if (btnRefreshMeta) {
          btnRefreshMeta.onclick = async () => {
            btnRefreshMeta.textContent = "Fetching...";
            btnRefreshMeta.disabled = true;
            try {
              const mRes = await fetch(`/api/series/${seriesId}/refresh-metadata`, { method: "POST" });
              const mData = await mRes.json();
              if (mData.success) {
                openSeriesModal(seriesId);
              } else {
                alert("Could not find online metadata for this series.");
              }
            } catch(err) {
              alert("Error fetching metadata: " + err.message);
            } finally {
              btnRefreshMeta.textContent = "🔄 Fetch MangaDex Metadata";
              btnRefreshMeta.disabled = false;
            }
          };
        }

        const chList = document.getElementById("modal-chapters-list");
        if (data.chapters && data.chapters.length > 0) {
          chList.innerHTML = data.chapters.map(c => `
            <div class="modal-chapter-row">
              <div>
                <strong>${c.title || `Chapter ${c.chapter_num}`}</strong>
                <span class="chapter-badge-format">${c.file_format || 'PDF'}</span>
                <span style="font-size: 0.8rem; color: var(--text-muted); margin-left: 0.5rem;">(${c.panel_count || 0} panels)</span>
              </div>
              <div style="display: flex; gap: 0.5rem;">
                ${c.status === 'completed' ? `<button class="btn btn-primary" style="padding: 0.3rem 0.8rem; font-size: 0.85rem;" onclick="openReader(${c.id})">📖 Read</button>` : `<span style="font-size: 0.8rem; color: var(--warning);">${c.status}</span>`}
                ${c.status === 'completed' ? `<a href="/api/download/file/${c.id}" class="btn btn-secondary" style="padding: 0.3rem 0.8rem; font-size: 0.85rem; text-decoration: none;" download>💾 File</a>` : ''}
              </div>
            </div>
          `).join("");
        } else {
          chList.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">No chapters recorded yet.</p>';
        }

        seriesModal.classList.remove("hidden");
      }
    } catch (e) {
      alert("Failed to load series: " + e.message);
    }
  };

  // --- Phone & OPDS Connectivity Modal ---
  const btnPhoneConnect = document.getElementById("btn-phone-connect");
  const phoneModal = document.getElementById("phone-modal");
  const phoneModalClose = document.getElementById("phone-modal-close");
  const phoneWebUrl = document.getElementById("phone-web-url");
  const phoneOpdsUrl = document.getElementById("phone-opds-url");
  const btnCopyPhoneUrl = document.getElementById("btn-copy-phone-url");
  const btnCopyOpdsUrl = document.getElementById("btn-copy-opds-url");

  if (btnPhoneConnect && phoneModal) {
    btnPhoneConnect.addEventListener("click", async () => {
      phoneModal.classList.remove("hidden");
      try {
        const res = await fetch("/api/network/info");
        const data = await res.json();
        if (data.success) {
          const currentHost = window.location.hostname;
          const currentPort = window.location.port || "8000";
          const resolvedIp = (currentHost !== "localhost" && currentHost !== "127.0.0.1") ? currentHost : data.lan_ip;
          phoneWebUrl.value = `http://${resolvedIp}:${currentPort}/`;
          phoneOpdsUrl.value = `http://${resolvedIp}:${currentPort}/opds/v1.2/catalog`;
        }
      } catch (err) {
        phoneWebUrl.value = `${window.location.origin}/`;
        phoneOpdsUrl.value = `${window.location.origin}/opds/v1.2/catalog`;
      }
    });
  }

  if (phoneModalClose && phoneModal) {
    phoneModalClose.addEventListener("click", () => {
      phoneModal.classList.add("hidden");
    });
  }

  if (btnCopyPhoneUrl) {
    btnCopyPhoneUrl.addEventListener("click", () => {
      navigator.clipboard.writeText(phoneWebUrl.value).then(() => {
        btnCopyPhoneUrl.textContent = "✅ Copied!";
        setTimeout(() => btnCopyPhoneUrl.textContent = "📋 Copy", 2000);
      });
    });
  }

  if (btnCopyOpdsUrl) {
    btnCopyOpdsUrl.addEventListener("click", () => {
      navigator.clipboard.writeText(phoneOpdsUrl.value).then(() => {
        btnCopyOpdsUrl.textContent = "✅ Copied!";
        setTimeout(() => btnCopyOpdsUrl.textContent = "📋 Copy", 2000);
      });
    });
  }

  // --- In-App Web Reader ---
  const readerView = document.getElementById("reader-view");
  const readerClose = document.getElementById("reader-close");
  const readerPagesContainer = document.getElementById("reader-pages-container");
  const readerSeriesTitle = document.getElementById("reader-series-title");
  const readerChapterTitle = document.getElementById("reader-chapter-title");
  const readerPrevBtn = document.getElementById("reader-prev-btn");
  const readerNextBtn = document.getElementById("reader-next-btn");
  const readerProgressCounter = document.getElementById("reader-progress-counter");
  const readerScrollTop = document.getElementById("reader-scroll-top");
  const readerFullscreenBtn = document.getElementById("reader-fullscreen-btn");
  const readerTopbar = document.querySelector(".reader-topbar");
  const readerBottomHud = document.querySelector(".reader-bottom-hud");

  let currentReadingChapterId = null;
  let lastReaderScrollTop = 0;
  let hudHidden = false;

  function setHudVisibility(visible) {
    hudHidden = !visible;
    if (readerTopbar) {
      if (visible) readerTopbar.classList.remove("hud-hidden");
      else readerTopbar.classList.add("hud-hidden");
    }
    if (readerBottomHud) {
      if (visible) readerBottomHud.classList.remove("hud-hidden");
      else readerBottomHud.classList.add("hud-hidden");
    }
  }

  // Tap in reading area toggles HUD (except on buttons or links)
  if (readerPagesContainer) {
    readerPagesContainer.addEventListener("click", (e) => {
      if (e.target.tagName === "BUTTON" || e.target.closest("button") || e.target.tagName === "A") {
        return;
      }
      setHudVisibility(hudHidden);
    });
  }

  // Fullscreen API toggle
  if (readerFullscreenBtn) {
    readerFullscreenBtn.addEventListener("click", () => {
      const isFs = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement;
      if (!isFs) {
        if (readerView.requestFullscreen) {
          readerView.requestFullscreen().catch(() => {});
        } else if (readerView.webkitRequestFullscreen) {
          readerView.webkitRequestFullscreen();
        } else if (document.documentElement.requestFullscreen) {
          document.documentElement.requestFullscreen().catch(() => {});
        }
      } else {
        if (document.exitFullscreen) {
          document.exitFullscreen().catch(() => {});
        } else if (document.webkitExitFullscreen) {
          document.webkitExitFullscreen();
        }
      }
    });

    const updateFsBtnText = () => {
      const isFs = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement;
      readerFullscreenBtn.textContent = isFs ? "✕ Exit" : "⛶ Fullscreen";
    };
    document.addEventListener("fullscreenchange", updateFsBtnText);
    document.addEventListener("webkitfullscreenchange", updateFsBtnText);
  }

  readerClose.addEventListener("click", () => {
    // If in fullscreen, exit fullscreen first
    if (document.fullscreenElement || document.webkitFullscreenElement) {
      if (document.exitFullscreen) document.exitFullscreen().catch(() => {});
      else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
    }
    readerView.classList.add("hidden");
    readerPagesContainer.innerHTML = "";
    currentReadingChapterId = null;
    loadLibrary();
  });

  readerScrollTop.addEventListener("click", () => {
    readerView.scrollTo({ top: 0, behavior: "smooth" });
  });

  window.openReader = async function(chapterId) {
    currentReadingChapterId = chapterId;
    setHudVisibility(true);
    seriesModal.classList.add("hidden");
    readerView.classList.remove("hidden");
    readerView.scrollTop = 0;
    readerPagesContainer.innerHTML = "<p style='color: #94a3b8; padding: 3rem; text-align: center;'>Loading chapter panels...</p>";

    try {
      const res = await fetch(`/api/chapter/${chapterId}/pages`);
      const data = await res.json();

      if (data.success && data.pages) {
        readerSeriesTitle.textContent = data.series_title;
        readerChapterTitle.textContent = data.chapter_title;
        readerProgressCounter.textContent = `Total ${data.total_pages} panels`;

        // Configure Prev / Next buttons
        if (data.prev_chapter_id) {
          readerPrevBtn.disabled = false;
          readerPrevBtn.onclick = () => openReader(data.prev_chapter_id);
        } else {
          readerPrevBtn.disabled = true;
        }

        if (data.next_chapter_id) {
          readerNextBtn.disabled = false;
          readerNextBtn.onclick = () => openReader(data.next_chapter_id);
        } else {
          readerNextBtn.disabled = true;
        }

        // Render panels in vertical continuous scroll
        const panelsHtml = data.pages.map((pUrl, idx) => `
          <div class="reader-page-wrapper" style="position: relative; display: inline-block; width: 100%; text-align: center;">
            <img class="reader-page" src="${pUrl}" alt="Page ${idx + 1}" loading="lazy" decoding="async" id="page-panel-${idx}">
            <button class="btn-mark-promo" onclick="markPageAsPromo(${chapterId}, ${idx}, this)" style="position: absolute; right: 15px; top: 15px; background: rgba(15,23,42,0.85); color: #f87171; border: 1px solid #ef4444; border-radius: 6px; padding: 4px 10px; font-size: 0.75rem; cursor: pointer; opacity: 0.4; transition: opacity 0.2s;" onmouseenter="this.style.opacity='1'" onmouseleave="this.style.opacity='0.4'">🚫 Mark as Promo</button>
          </div>
        `).join("");

        // End-of-chapter card for seamless mobile navigation
        const endCardHtml = `
          <div class="reader-chapter-end-card" style="width: 90%; max-width: 500px; margin: 3rem auto 2rem auto; padding: 2rem 1.5rem; text-align: center; background: rgba(30, 41, 59, 0.85); border: 1px solid var(--border-color); border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.5);">
            <h3 style="margin-bottom: 0.5rem; font-size: 1.2rem; color: var(--text-main);">Finished ${data.chapter_title} 🎉</h3>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1.5rem;">${data.series_title}</p>
            <div style="display: flex; flex-direction: column; gap: 0.75rem; justify-content: center; align-items: stretch; max-width: 280px; margin: 0 auto;">
              ${data.next_chapter_id 
                ? `<button class="btn btn-primary" style="padding: 12px 18px; font-size: 0.95rem; font-weight: 600;" onclick="openReader(${data.next_chapter_id})">Next Chapter ❯</button>` 
                : '<p style="color: #4ade80; font-size: 0.85rem; margin: 4px 0;">🎉 You are caught up to the latest downloaded chapter!</p>'
              }
              ${data.prev_chapter_id 
                ? `<button class="btn btn-secondary" style="padding: 10px 16px; font-size: 0.85rem;" onclick="openReader(${data.prev_chapter_id})">❮ Previous Chapter</button>` 
                : ''
              }
              <button class="btn btn-secondary" style="padding: 10px 16px; font-size: 0.85rem;" onclick="readerClose.click()">Back to Library</button>
            </div>
          </div>
        `;

        readerPagesContainer.innerHTML = panelsHtml + endCardHtml;

        // Scroll listener for progress tracking and auto-hiding HUD
        let progressSaveTimeout = null;
        readerView.onscroll = () => {
          const currentScroll = readerView.scrollTop;
          const diff = currentScroll - lastReaderScrollTop;

          // Auto-hide HUD on downward scroll, reveal on upward scroll
          if (diff > 35 && currentScroll > 80 && !hudHidden) {
            setHudVisibility(false);
          } else if (diff < -25 && hudHidden) {
            setHudVisibility(true);
          }
          lastReaderScrollTop = Math.max(0, currentScroll);

          const scrollPos = readerView.scrollTop + 300;
          const panels = readerPagesContainer.querySelectorAll(".reader-page");
          let currentPage = 1;
          panels.forEach((p, i) => {
            if (p.offsetTop <= scrollPos) {
              currentPage = i + 1;
            }
          });
          readerProgressCounter.textContent = `Page ${currentPage} of ${data.total_pages}`;

          // Throttle progress save
          if (!progressSaveTimeout) {
            progressSaveTimeout = setTimeout(() => {
              progressSaveTimeout = null;
              fetch(`/api/chapter/${chapterId}/progress`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ last_read_page: currentPage, read_status: 1 })
              }).catch(() => {});
            }, 1000);
          }
        };
      } else {
        readerPagesContainer.innerHTML = `<p style="color: var(--danger); padding: 3rem; text-align: center;">Error: ${data.error || 'Could not load chapter pages.'}</p>`;
      }
    } catch (e) {
      readerPagesContainer.innerHTML = `<p style="color: var(--danger); padding: 3rem; text-align: center;">Network error: ${e.message}</p>`;
    }
  };

  window.markPageAsPromo = async function(chapterId, pageIndex, btnElem) {
    if (!confirm(`Mark Page ${pageIndex + 1} as a recurring promotional/ad page? It will be automatically trimmed from future downloads.`)) {
      return;
    }
    btnElem.textContent = "Fingerprinting...";
    btnElem.disabled = true;
    try {
      const res = await fetch("/api/promos/mark", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chapter_id: chapterId, page_index: pageIndex, label: `Page ${pageIndex + 1} Promo` })
      });
      const data = await res.json();
      if (data.success) {
        btnElem.textContent = "✅ Blocked";
        btnElem.style.color = "#10b981";
        btnElem.style.borderColor = "#10b981";
        btnElem.style.opacity = "1";
        alert("✅ Promotional page fingerprinted! Future chapter downloads will automatically trim this ad.");
      } else {
        alert("Error marking promo: " + (data.error || "Unknown error"));
        btnElem.textContent = "🚫 Mark as Promo";
        btnElem.disabled = false;
      }
    } catch (e) {
      alert("Network error: " + e.message);
      btnElem.textContent = "🚫 Mark as Promo";
      btnElem.disabled = false;
    }
  };

  // --- Diagnostic Lab Tab ---
  const labUrlInput = document.getElementById("lab-url");
  const btnLabTest = document.getElementById("btn-lab-test");
  const labResult = document.getElementById("lab-result");

  // Preset click handlers
  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      labUrlInput.value = btn.getAttribute("data-url");
    });
  });

  btnLabTest.addEventListener("click", async () => {
    const url = labUrlInput.value.trim();
    if (!url) {
      alert("Please paste a URL to test.");
      return;
    }

    btnLabTest.textContent = "Testing...";
    btnLabTest.disabled = true;

    try {
      const res = await fetch("/api/lab/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await res.json();

      labResult.classList.remove("hidden");
      if (data.success && data.diagnostic) {
        const d = data.diagnostic;
        labResult.innerHTML = `
          <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid var(--success); padding: 1rem; border-radius: 8px;">
            <h4 style="color: var(--success); margin-bottom: 0.5rem;">✅ TEST PASSED</h4>
            <p><strong>Engine Detected:</strong> ${d.engine_name}</p>
            <p><strong>Series Title:</strong> ${d.series_title}</p>
            <p><strong>Panels Isolated:</strong> ${d.panel_count} clean panels</p>
            <p><strong>Next Chapter Link:</strong> ${d.next_chapter_url ? d.next_chapter_url : "None in DOM (Smart fallback active)"}</p>
          </div>
        `;
      } else {
        labResult.innerHTML = `
          <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid var(--danger); padding: 1rem; border-radius: 8px;">
            <h4 style="color: var(--danger); margin-bottom: 0.5rem;">❌ TEST FAILED</h4>
            <p>${data.error || "Site could not be parsed."}</p>
          </div>
        `;
      }
      loadDiagnosticsTable();
    } catch (err) {
      labResult.innerHTML = `<p style="color: var(--danger);">Network error: ${err.message}</p>`;
      labResult.classList.remove("hidden");
    } finally {
      btnLabTest.textContent = "Run Test";
      btnLabTest.disabled = false;
    }
  });

  async function loadDiagnosticsTable() {
    const tbody = document.getElementById("diagnostic-tbody");
    try {
      const res = await fetch("/api/lab/sites");
      const data = await res.json();
      if (data.success && data.diagnostics && data.diagnostics.length > 0) {
        tbody.innerHTML = data.diagnostics.map((d) => `
          <tr>
            <td><strong>${d.domain}</strong></td>
            <td>${d.engine_detected || 'Unknown'}</td>
            <td><span class="${d.status === 'PASS' ? 'badge-pass' : 'badge-blocked'}">${d.status}</span></td>
            <td>${d.panels_found}</td>
            <td>${d.next_chapter_found ? '✅ Yes' : '❌ Fallback'}</td>
            <td>${new Date(d.last_checked).toLocaleDateString()}</td>
          </tr>
        `).join("");
      }
    } catch (e) {
      console.error("Error loading diagnostics table", e);
    }
  }

  // --- Settings Tab Handlers ---
  async function loadSettings() {
    try {
      const res = await fetch("/api/settings");
      const data = await res.json();
      if (data.success && data.settings) {
        const s = data.settings;
        if (s.auto_update_enabled) document.getElementById("setting-auto-update").value = s.auto_update_enabled;
        if (s.auto_update_interval_hours) document.getElementById("setting-interval").value = s.auto_update_interval_hours;
        if (s.preferred_format) document.getElementById("setting-preferred-format").value = s.preferred_format;
        if (s.discord_webhook_url) document.getElementById("setting-discord-webhook").value = s.discord_webhook_url;
        if (s.ntfy_topic_url) document.getElementById("setting-ntfy-topic").value = s.ntfy_topic_url;
        if (s.telegram_bot_token) document.getElementById("setting-telegram-token").value = s.telegram_bot_token;
        if (s.telegram_chat_id) document.getElementById("setting-telegram-chat").value = s.telegram_chat_id;
        if (s.anilist_enabled) document.getElementById("setting-anilist-enabled").value = s.anilist_enabled;
        if (s.anilist_token) document.getElementById("setting-anilist-token").value = s.anilist_token;
        if (s.mal_enabled) document.getElementById("setting-mal-enabled").value = s.mal_enabled;
        if (s.mal_token) document.getElementById("setting-mal-token").value = s.mal_token;
        if (s.flaresolverr_url) document.getElementById("setting-flaresolverr-url").value = s.flaresolverr_url;
        if (s.ai_upscaler_url) document.getElementById("setting-upscaler-url").value = s.ai_upscaler_url;
      }
      loadPromoSignatures();
    } catch (e) {
      console.error("Error loading settings", e);
    }
  }

  async function loadPromoSignatures() {
    const listElem = document.getElementById("promo-signatures-list");
    if (!listElem) return;
    try {
      const res = await fetch("/api/promos");
      const data = await res.json();
      if (data.success && data.signatures && data.signatures.length > 0) {
        listElem.innerHTML = data.signatures.map(s => `
          <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(30, 41, 59, 0.5); padding: 8px 14px; border-radius: 6px; margin-bottom: 6px; border: 1px solid var(--border);">
            <div>
              <strong>${s.label || 'Promo'}</strong>
              <span style="font-family: monospace; font-size: 0.8rem; color: var(--text-muted); margin-left: 8px;">${s.phash.slice(0, 16)}...</span>
            </div>
            <button onclick="deletePromo(${s.id})" class="btn btn-secondary" style="color: #f87171; border-color: #ef4444; padding: 2px 8px; font-size: 0.75rem;">Delete</button>
          </div>
        `).join("");
      } else {
        listElem.innerHTML = '<p style="color: var(--text-muted); font-size: 0.9rem;">No promotional page signatures registered yet. Mark pages in the Web Reader to auto-filter them!</p>';
      }
    } catch (e) {
      listElem.innerHTML = '<p style="color: var(--danger);">Failed to load signatures.</p>';
    }
  }

  window.deletePromo = async function(id) {
    if (!confirm("Delete this promotional filter signature?")) return;
    try {
      const res = await fetch(`/api/promos/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) {
        loadPromoSignatures();
      }
    } catch (e) {
      alert("Error deleting signature: " + e.message);
    }
  };

  const btnVerifyAnilist = document.getElementById("btn-verify-anilist");
  if (btnVerifyAnilist) {
    btnVerifyAnilist.addEventListener("click", async () => {
      const token = document.getElementById("setting-anilist-token").value.trim();
      if (!token) return alert("Please paste an AniList token first.");
      btnVerifyAnilist.textContent = "Checking...";
      btnVerifyAnilist.disabled = true;
      const statusElem = document.getElementById("anilist-status");
      try {
        const res = await fetch("/api/tracker/verify/anilist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token })
        });
        const data = await res.json();
        if (data.success) {
          statusElem.style.color = "var(--success)";
          statusElem.textContent = `✅ Connected as: ${data.username} (ID: ${data.user_id})`;
        } else {
          statusElem.style.color = "var(--danger)";
          statusElem.textContent = `❌ Verification failed: ${data.error}`;
        }
      } catch (e) {
        statusElem.style.color = "var(--danger)";
        statusElem.textContent = `❌ Network error: ${e.message}`;
      } finally {
        btnVerifyAnilist.textContent = "Verify";
        btnVerifyAnilist.disabled = false;
      }
    });
  }

  const btnVerifyMal = document.getElementById("btn-verify-mal");
  if (btnVerifyMal) {
    btnVerifyMal.addEventListener("click", async () => {
      const token = document.getElementById("setting-mal-token").value.trim();
      if (!token) return alert("Please paste a MyAnimeList access token first.");
      btnVerifyMal.textContent = "Checking...";
      btnVerifyMal.disabled = true;
      const statusElem = document.getElementById("mal-status");
      try {
        const res = await fetch("/api/tracker/verify/mal", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token })
        });
        const data = await res.json();
        if (data.success) {
          statusElem.style.color = "var(--success)";
          statusElem.textContent = `✅ Connected as: ${data.username} (ID: ${data.user_id})`;
        } else {
          statusElem.style.color = "var(--danger)";
          statusElem.textContent = `❌ Verification failed: ${data.error}`;
        }
      } catch (e) {
        statusElem.style.color = "var(--danger)";
        statusElem.textContent = `❌ Network error: ${e.message}`;
      } finally {
        btnVerifyMal.textContent = "Verify";
        btnVerifyMal.disabled = false;
      }
    });
  }

  const btnSaveSettings = document.getElementById("btn-save-settings");
  if (btnSaveSettings) {
    btnSaveSettings.addEventListener("click", async () => {
      const payload = {
        auto_update_enabled: document.getElementById("setting-auto-update").value,
        auto_update_interval_hours: document.getElementById("setting-interval").value,
        preferred_format: document.getElementById("setting-preferred-format").value,
        discord_webhook_url: document.getElementById("setting-discord-webhook").value.trim(),
        ntfy_topic_url: document.getElementById("setting-ntfy-topic").value.trim(),
        telegram_bot_token: document.getElementById("setting-telegram-token").value.trim(),
        telegram_chat_id: document.getElementById("setting-telegram-chat").value.trim(),
        anilist_enabled: document.getElementById("setting-anilist-enabled").value,
        anilist_token: document.getElementById("setting-anilist-token").value.trim(),
        mal_enabled: document.getElementById("setting-mal-enabled").value,
        mal_token: document.getElementById("setting-mal-token").value.trim(),
        flaresolverr_url: document.getElementById("setting-flaresolverr-url") ? document.getElementById("setting-flaresolverr-url").value.trim() : "",
        ai_upscaler_url: document.getElementById("setting-upscaler-url") ? document.getElementById("setting-upscaler-url").value.trim() : ""
      };

      btnSaveSettings.textContent = "Saving...";
      btnSaveSettings.disabled = true;

      try {
        const res = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        const msg = document.getElementById("settings-status-msg");
        if (data.success) {
          msg.textContent = "✅ Settings successfully saved!";
          msg.classList.remove("hidden");
          setTimeout(() => msg.classList.add("hidden"), 3000);
        }
      } catch (e) {
        alert("Failed to save settings: " + e.message);
      } finally {
        btnSaveSettings.textContent = "💾 Save Settings";
        btnSaveSettings.disabled = false;
      }
    });
  }

  const btnTestDiscord = document.getElementById("btn-test-discord");
  if (btnTestDiscord) {
    btnTestDiscord.addEventListener("click", async () => {
      const target = document.getElementById("setting-discord-webhook").value.trim();
      if (!target) return alert("Please enter a Discord Webhook URL first.");
      btnTestDiscord.textContent = "Testing...";
      btnTestDiscord.disabled = true;
      try {
        const res = await fetch("/api/settings/test-notification", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channel: "discord", target })
        });
        const data = await res.json();
        alert(data.success ? "✅ Discord webhook test sent successfully!" : "❌ Discord webhook test failed. Verify URL.");
      } catch (e) {
        alert("Test error: " + e.message);
      } finally {
        btnTestDiscord.textContent = "Test Discord";
        btnTestDiscord.disabled = false;
      }
    });
  }

  const btnTestNtfy = document.getElementById("btn-test-ntfy");
  if (btnTestNtfy) {
    btnTestNtfy.addEventListener("click", async () => {
      const target = document.getElementById("setting-ntfy-topic").value.trim();
      if (!target) return alert("Please enter an Ntfy Topic URL first.");
      btnTestNtfy.textContent = "Testing...";
      btnTestNtfy.disabled = true;
      try {
        const res = await fetch("/api/settings/test-notification", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channel: "ntfy", target })
        });
        const data = await res.json();
        alert(data.success ? "✅ Ntfy push test sent successfully!" : "❌ Ntfy push test failed.");
      } catch (e) {
        alert("Test error: " + e.message);
      } finally {
        btnTestNtfy.textContent = "Test Ntfy";
        btnTestNtfy.disabled = false;
      }
    });
  }

  const btnTestFlaresolverr = document.getElementById("btn-test-flaresolverr");
  if (btnTestFlaresolverr) {
    btnTestFlaresolverr.addEventListener("click", async () => {
      const url = document.getElementById("setting-flaresolverr-url").value.trim() || "http://localhost:8191/v1";
      btnTestFlaresolverr.textContent = "Testing...";
      btnTestFlaresolverr.disabled = true;
      const statusElem = document.getElementById("flaresolverr-status");
      try {
        const res = await fetch("/api/settings/test-flaresolverr", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (data.success) {
          statusElem.style.color = "var(--success)";
          statusElem.textContent = "✅ FlareSolverr is online and accessible!";
        } else {
          statusElem.style.color = "var(--danger)";
          statusElem.textContent = "❌ Could not reach FlareSolverr container. Check URL and Docker container status.";
        }
      } catch (e) {
        statusElem.style.color = "var(--danger)";
        statusElem.textContent = "❌ Network error: " + e.message;
      } finally {
        btnTestFlaresolverr.textContent = "Test Connection";
        btnTestFlaresolverr.disabled = false;
      }
    });
  }

  const btnTestUpscaler = document.getElementById("btn-test-upscaler");
  if (btnTestUpscaler) {
    btnTestUpscaler.addEventListener("click", async () => {
      const url = document.getElementById("setting-upscaler-url").value.trim() || "http://localhost:5000/upscale";
      btnTestUpscaler.textContent = "Testing...";
      btnTestUpscaler.disabled = true;
      const statusElem = document.getElementById("upscaler-status");
      try {
        const res = await fetch("/api/settings/test-upscaler", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url })
        });
        const data = await res.json();
        const statRes = await fetch("/api/settings/upscaler-status");
        const statData = await statRes.json();
        const statusObj = (statData && statData.status) || {};

        const localEngines = [];
        if (statusObj.waifu2x_cli) localEngines.push("waifu2x-ncnn-vulkan");
        if (statusObj.realesrgan_cli) localEngines.push("realesrgan-ncnn-vulkan");

        let msg = "";
        if (data.success) {
          msg = "✅ AI Upscaler microservice is online!";
          statusElem.style.color = "var(--success)";
        } else {
          msg = "ℹ️ REST API offline. ";
          if (localEngines.length > 0) {
            msg += `Local CLI detected (${localEngines.join(", ")}).`;
            statusElem.style.color = "var(--success)";
          } else {
            msg += "Lanczos-4 high-quality fallback will be used.";
            statusElem.style.color = "var(--warning)";
          }
        }
        statusElem.textContent = msg;
      } catch (e) {
        statusElem.style.color = "var(--danger)";
        statusElem.textContent = "❌ Network error: " + e.message;
      } finally {
        btnTestUpscaler.textContent = "Test Connection";
        btnTestUpscaler.disabled = false;
      }
    });
  }



  // Switch tabs also triggers promo list load if settings tab
  const settingsTabBtn = document.querySelector('[data-tab="settings"]');
  if (settingsTabBtn) {
    settingsTabBtn.addEventListener("click", () => {
      loadSettings();
    });
  }

  // Initial load
  loadLibrary();
  listenToProgress();
});


