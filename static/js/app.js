// YouTube Clipper Pro - Interactive Client & Social Publishing Studio

document.addEventListener("DOMContentLoaded", () => {
  // ==========================================================
  // 1. APPLICATION STATE
  // ==========================================================
  let currentVideoInfo = null;
  let selectedRatio = "9:16";
  let selectedResolution = "1080p";
  let selectedSubtitle = "tiktok";
  let selectedFaceTracking = "single"; // "single" | "dynamic" | "split" | "none"
  let lastFolderPath = null;
  let activeEventSource = null;
  let expandedProjects = new Set();
  let currentPublishClip = null;
  let activePublishPollInterval = null;

  // Gallery & Channel Grouping State
  let rawGalleryItems = [];
  let activeChannelFilter = "ALL";
  let galleryGroupBy = "video"; // "video" | "channel"

  // ==========================================================
  // 2. DOM ELEMENT REFERENCES
  // ==========================================================
  // URL Input & Hero Elements
  const urlInput = document.getElementById("youtube-url");
  const btnPaste = document.getElementById("btn-paste");
  const btnFetch = document.getElementById("btn-fetch");
  const fetchText = document.getElementById("fetch-text");
  const fetchSpinner = document.getElementById("fetch-spinner");

  // Video Preview Elements
  const previewCard = document.getElementById("video-preview-card");
  const previewThumb = document.getElementById("preview-thumb");
  const previewDuration = document.getElementById("preview-duration");
  const previewTitle = document.getElementById("preview-title");
  const previewChannel = document.getElementById("preview-channel");
  const badgeCached = document.getElementById("badge-cached");
  const badgeResolution = document.getElementById("badge-resolution");
  const badgeCaptions = document.getElementById("badge-captions");
  const badgeViews = document.getElementById("badge-views");
  const cacheNoticeText = document.getElementById("cache-notice-text");

  // Preferences Elements
  const preferencesPanel = document.getElementById("preferences-panel");
  const clipCountSlider = document.getElementById("clip-count-slider");
  const clipCountVal = document.getElementById("clip-count-val");
  const clipDurationSlider = document.getElementById("clip-duration-slider");
  const clipDurationVal = document.getElementById("clip-duration-val");
  const btnGenerate = document.getElementById("btn-generate");

  // Loader Elements
  const loaderModal = document.getElementById("loader-modal");
  const loaderPercent = document.getElementById("loader-percent");
  const loaderTitle = document.getElementById("loader-title");
  const loaderSubtitle = document.getElementById("loader-subtitle");
  const progressBarFill = document.getElementById("progress-bar-fill");
  const stages = {
    info: document.getElementById("stage-info"),
    download: document.getElementById("stage-download"),
    face: document.getElementById("stage-face"),
    render: document.getElementById("stage-render"),
    save: document.getElementById("stage-save"),
  };

  // Active Results Section Elements
  const resultsSection = document.getElementById("results-section");
  const resultsFolderPath = document.getElementById("results-folder-path");
  const btnOpenResultFolder = document.getElementById("btn-open-result-folder");
  const clipsGrid = document.getElementById("clips-grid");

  // Dashboard Gallery & Channel Grouping Elements
  const headerLibraryCount = document.getElementById("header-library-count");
  const galleryVideoCount = document.getElementById("gallery-video-count");
  const galleryClipTotal = document.getElementById("gallery-clip-total");
  const dashboardGalleryGrid = document.getElementById("dashboard-gallery-grid");
  const channelChipsContainer = document.getElementById("channel-chips-container");
  const galleryFilterBar = document.getElementById("gallery-filter-bar");
  const toggleViewVideo = document.getElementById("toggle-view-video");
  const toggleViewChannel = document.getElementById("toggle-view-channel");

  // Social Auth Modal Elements
  const btnOpenSocialModal = document.getElementById("btn-open-social-modal");
  const connectedPlatformsCount = document.getElementById("connected-platforms-count");
  const socialModal = document.getElementById("social-modal");
  const btnCloseSocialModal = document.getElementById("btn-close-social-modal");

  // One-Click Social Publish Modal Elements
  const publishModal = document.getElementById("publish-modal");
  const btnClosePublish = document.getElementById("btn-close-publish");
  const btnCancelPublish = document.getElementById("btn-cancel-publish");
  const btnStartPublish = document.getElementById("btn-start-publish");
  const publishBtnText = document.getElementById("publish-btn-text");
  const publishSpinner = document.getElementById("publish-spinner");
  const publishTitleInput = document.getElementById("publish-title");
  const publishDescInput = document.getElementById("publish-desc");
  const btnSelectAllPlatforms = document.getElementById("btn-select-all-platforms");
  const btnClearPlatforms = document.getElementById("btn-clear-platforms");
  const publishLiveFeedback = document.getElementById("publish-live-feedback");
  const publishLiveLoader = document.getElementById("publish-live-loader");

  // Post History Elements
  const btnOpenHistoryModal = document.getElementById("btn-open-history-modal");
  const historyCountBadge = document.getElementById("history-count-badge");
  const historyModal = document.getElementById("history-modal");
  const btnCloseHistory = document.getElementById("btn-close-history");
  const btnClearHistory = document.getElementById("btn-clear-history");
  const historyItemsContainer = document.getElementById("history-items-container");

  // ==========================================================
  // 3. UI CONTROLS & OPTION SELECTORS
  // ==========================================================
  function setupOptionGroup(groupId, onSelect) {
    const container = document.getElementById(groupId);
    if (!container) return;
    const cards = container.querySelectorAll(".option-card");
    cards.forEach((card) => {
      card.addEventListener("click", () => {
        cards.forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        onSelect(card.dataset.value);
      });
    });
  }

  setupOptionGroup("ratio-options", (val) => (selectedRatio = val));
  setupOptionGroup("res-options", (val) => (selectedResolution = val));
  setupOptionGroup("sub-options", (val) => (selectedSubtitle = val));
  setupOptionGroup("face-tracking-options", (val) => (selectedFaceTracking = val));

  // Sliders
  if (clipCountSlider) {
    clipCountSlider.addEventListener("input", (e) => {
      clipCountVal.textContent = `${e.target.value} ${e.target.value == 1 ? "Clip" : "Clips"}`;
    });
  }

  if (clipDurationSlider) {
    clipDurationSlider.addEventListener("input", (e) => {
      clipDurationVal.textContent = `${e.target.value}s`;
    });
  }

  // Paste Action
  if (btnPaste) {
    btnPaste.addEventListener("click", async () => {
      try {
        const text = await navigator.clipboard.readText();
        if (text) {
          urlInput.value = text.trim();
          urlInput.focus();
          fetchVideoInfo();
        }
      } catch (err) {
        console.warn("Clipboard notice:", err);
      }
    });
  }

  // Fetch Video Info Handlers
  if (btnFetch) btnFetch.addEventListener("click", () => fetchVideoInfo());
  if (urlInput) {
    urlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") fetchVideoInfo();
    });
  }

  async function fetchVideoInfo(customUrl = null) {
    const url = (customUrl || urlInput.value).trim();
    if (!url) {
      alert("Please enter a valid YouTube URL.");
      return;
    }

    urlInput.value = url;
    fetchText.textContent = "Inspecting...";
    fetchSpinner.style.display = "inline";
    btnFetch.disabled = true;

    try {
      const res = await fetch("/api/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || "Failed to inspect video.");
      }

      currentVideoInfo = data.data || data.info || {};
      if (!currentVideoInfo || !currentVideoInfo.title) {
        throw new Error("Could not retrieve video information from server response.");
      }

      displayVideoPreview(currentVideoInfo);
      preferencesPanel.style.display = "block";
      preferencesPanel.scrollIntoView({ behavior: "smooth" });
    } catch (err) {
      alert(`Error: ${err.message}`);
    } finally {
      fetchText.textContent = "Inspect Video";
      fetchSpinner.style.display = "none";
      btnFetch.disabled = false;
    }
  }

  function displayVideoPreview(info) {
    if (!info) return;
    const thumbUrl = info.thumbnail || (info.id ? `https://img.youtube.com/vi/${info.id}/hqdefault.jpg` : "");
    previewThumb.src = thumbUrl;
    previewDuration.textContent = formatDuration(info.duration);
    previewTitle.textContent = info.title || "YouTube Video";
    previewChannel.textContent = info.channel || "Creator";

    if (info.is_cached) {
      badgeCached.style.display = "inline-flex";
      if (cacheNoticeText) cacheNoticeText.style.display = "block";
    } else {
      badgeCached.style.display = "none";
      if (cacheNoticeText) cacheNoticeText.style.display = "none";
    }

    const maxRes = (info.available_resolutions && info.available_resolutions.length > 0)
      ? info.available_resolutions[0]
      : (info.resolution || "1080p");
    badgeResolution.textContent = `📺 ${maxRes} Max`;
    badgeCaptions.textContent = info.has_captions ? "💬 Captions Available" : "🔇 No Captions (Clean Subtitles)";
    badgeViews.textContent = `👁️ ${formatNumber(info.view_count)} views`;

    previewCard.style.display = "grid";
  }

  function formatDuration(sec) {
    if (!sec) return "00:00";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  function formatNumber(num) {
    if (!num) return "0";
    if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
    if (num >= 1000) return (num / 1000).toFixed(1) + "K";
    return num.toLocaleString();
  }

  // ==========================================================
  // 4. GENERATE VIDEO CLIPS (SSE PIPELINE)
  // ==========================================================
  if (btnGenerate) {
    btnGenerate.addEventListener("click", () => {
      if (!currentVideoInfo) return;

      const payload = {
        url: currentVideoInfo.url,
        video_id: currentVideoInfo.id || currentVideoInfo.video_id,
        clip_count: parseInt(clipCountSlider.value, 10),
        target_duration: parseFloat(clipDurationSlider.value),
        aspect_ratio: selectedRatio,
        resolution: selectedResolution,
        face_follow: selectedFaceTracking,
        subtitle_option: selectedSubtitle,
      };

      startGenerationPipeline(payload);
    });
  }

  async function startGenerationPipeline(payload) {
    resetLoaderStages();
    loaderModal.classList.add("active");

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.detail || "Failed to start generation.");
      }

      const jobId = data.job_id;
      listenToProgress(jobId);
    } catch (err) {
      loaderModal.classList.remove("active");
      alert(`Generation failed to start: ${err.message}`);
    }
  }

  function resetLoaderStages() {
    loaderPercent.textContent = "0%";
    progressBarFill.style.width = "0%";
    loaderTitle.textContent = "Processing Video";
    loaderSubtitle.textContent = "Initializing clipping engine...";

    Object.values(stages).forEach((el) => {
      if (el) el.className = "stage-item";
    });
  }

  function listenToProgress(jobId) {
    if (activeEventSource) {
      activeEventSource.close();
    }

    activeEventSource = new EventSource(`/api/progress/${jobId}`);

    activeEventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      updateLoaderUI(data);

      if (data.stage === "completed") {
        activeEventSource.close();
        activeEventSource = null;
        setTimeout(() => {
          loaderModal.classList.remove("active");
          displayActiveResults(data);
          refreshDashboardGallery();
        }, 1200);
      } else if (data.stage === "error") {
        activeEventSource.close();
        activeEventSource = null;
        loaderTitle.textContent = "Error Occurred";
        loaderSubtitle.textContent = data.message || "An unexpected error occurred.";
        setTimeout(() => {
          loaderModal.classList.remove("active");
          alert(`Processing Error: ${data.message}`);
        }, 2000);
      }
    };

    activeEventSource.onerror = () => {
      console.warn("SSE connection interrupted.");
    };
  }

  function updateLoaderUI(data) {
    const pct = Math.min(100, Math.max(0, Math.round(data.progress || 0)));
    loaderPercent.textContent = `${pct}%`;
    progressBarFill.style.width = `${pct}%`;
    loaderSubtitle.textContent = data.message || "Processing video...";

    const stageMap = {
      starting: "info",
      fetching_info: "info",
      transcribing: "info",
      info: "info",
      downloading: "download",
      download: "download",
      face: "face",
      clipping: "render",
      rendering: "render",
      render: "render",
      saving: "save",
      save: "save",
      completed: "completed",
    };

    const activeStageKey = stageMap[data.stage] || "info";
    const stageOrder = ["info", "download", "face", "render", "save"];
    const currentIdx = stageOrder.indexOf(activeStageKey);

    stageOrder.forEach((st, idx) => {
      const el = stages[st];
      if (!el) return;

      if (data.stage === "completed" || (currentIdx !== -1 && idx < currentIdx)) {
        el.className = "stage-item completed";
      } else if (currentIdx !== -1 && idx === currentIdx) {
        el.className = "stage-item active";
      } else {
        el.className = "stage-item";
      }
    });
  }

  function displayActiveResults(data) {
    lastFolderPath = data.folder_path;
    resultsFolderPath.textContent = `Folder: output/${data.folder_name}`;
    resultsSection.style.display = "block";
    clipsGrid.innerHTML = "";

    const clips = data.clips || [];
    clips.forEach((clip) => {
      const card = document.createElement("div");
      card.className = "clip-card";

      const clipRatio = clip.aspect_ratio || selectedRatio;
      const ratioClass =
        clipRatio === "16:9"
          ? "ratio-16-9"
          : clipRatio === "1:1"
          ? "ratio-1-1"
          : clipRatio === "4:5"
          ? "ratio-4-5"
          : "";
      const clipRes = clip.resolution || selectedResolution;
      const clipFF = clip.face_follow !== undefined ? clip.face_follow : selectedFaceTracking;
      let ffBadgeHtml = "";
      if (clipFF === "dynamic") {
        ffBadgeHtml = '<span class="badge badge-overlay">🔄 Dynamic Pan</span>';
      } else if (clipFF === "split") {
        ffBadgeHtml = '<span class="badge badge-overlay">👥 Dual Podcast</span>';
      } else if (clipFF === "single" || clipFF === true) {
        ffBadgeHtml = '<span class="badge badge-overlay">👤 Single Speaker</span>';
      }

      card.innerHTML = `
        <div class="clip-media-container">
          <video class="clip-video-player ${ratioClass}" controls preload="metadata" playsinline>
            <source src="${clip.relative_url}" type="video/mp4">
          </video>
          <div class="clip-overlay-badges">
            <span class="badge badge-blue badge-overlay">📱 ${clipRatio}</span>
            <span class="badge badge-overlay">📺 ${clipRes}</span>
            ${ffBadgeHtml}
          </div>
        </div>
        <div class="clip-card-body">
          <div class="clip-title">${clip.title}</div>
          <div class="clip-meta-row">
            <span>⏱️ ${clip.duration_formatted}</span>
            <span>💾 ${clip.size_mb} MB</span>
            <span>${clip.has_srt ? "💬 Captions" : "🔇 Clean"}</span>
          </div>
          <div class="clip-actions">
            <button class="btn btn-publish btn-sm btn-open-publish" 
              data-path="${clip.file_path}" 
              data-title="${clip.title.replace(/"/g, '&quot;')}"
              title="One-Click Publish to YouTube, TikTok, Instagram">
              🚀 Publish
            </button>
            <a href="${clip.relative_url}" download="${clip.filename}" class="btn btn-primary btn-sm">
              ⬇️ MP4
            </a>
            ${
              clip.has_srt
                ? `<a href="${clip.srt_url}" download class="btn btn-secondary btn-sm" title="Download Subtitle SRT">📄 SRT</a>`
                : ""
            }
          </div>
        </div>
      `;

      const videoEl = card.querySelector("video");
      const mediaContainer = card.querySelector(".clip-media-container");
      if (videoEl && mediaContainer) {
        videoEl.addEventListener("play", () => mediaContainer.classList.add("is-playing"));
        videoEl.addEventListener("pause", () => mediaContainer.classList.remove("is-playing"));
        videoEl.addEventListener("ended", () => mediaContainer.classList.remove("is-playing"));
      }

      card.querySelector(".btn-open-publish").addEventListener("click", (e) => {
        openPublishModal({
          file_path: e.currentTarget.dataset.path,
          title: e.currentTarget.dataset.title,
        });
      });

      clipsGrid.appendChild(card);
    });

    resultsSection.scrollIntoView({ behavior: "smooth" });
  }

  // ==========================================================
  // 5. DASHBOARD GALLERY & CHANNEL GROUPING LOGIC
  // ==========================================================
  if (toggleViewVideo) {
    toggleViewVideo.addEventListener("click", () => {
      galleryGroupBy = "video";
      toggleViewVideo.classList.add("active");
      if (toggleViewChannel) toggleViewChannel.classList.remove("active");
      renderGalleryView();
    });
  }

  if (toggleViewChannel) {
    toggleViewChannel.addEventListener("click", () => {
      galleryGroupBy = "channel";
      toggleViewChannel.classList.add("active");
      if (toggleViewVideo) toggleViewVideo.classList.remove("active");
      renderGalleryView();
    });
  }

  async function refreshDashboardGallery() {
    try {
      const res = await fetch("/api/library");
      const data = await res.json();
      if (!data.success) return;

      rawGalleryItems = data.items || [];
      const totalClips = rawGalleryItems.reduce((sum, item) => sum + (item.clips ? item.clips.length : 0), 0);

      if (headerLibraryCount) headerLibraryCount.textContent = rawGalleryItems.length;
      if (galleryVideoCount) galleryVideoCount.textContent = rawGalleryItems.length;
      if (galleryClipTotal) galleryClipTotal.textContent = totalClips;

      renderChannelFilterChips();
      renderGalleryView();
    } catch (err) {
      console.warn("Failed to refresh gallery:", err);
    }
  }

  function renderChannelFilterChips() {
    if (!channelChipsContainer) return;

    // Count projects per YouTube channel
    const channelCounts = {};
    rawGalleryItems.forEach((item) => {
      const ch = (item.channel || "YouTube Channel").trim();
      channelCounts[ch] = (channelCounts[ch] || 0) + 1;
    });

    const channelsList = Object.keys(channelCounts).sort();

    if (channelsList.length === 0) {
      if (galleryFilterBar) galleryFilterBar.style.display = "none";
      return;
    }
    if (galleryFilterBar) galleryFilterBar.style.display = "flex";

    let html = `
      <button type="button" class="channel-chip ${activeChannelFilter === "ALL" ? "active" : ""}" data-channel="ALL">
        ✨ All Channels (${rawGalleryItems.length})
      </button>
    `;

    channelsList.forEach((ch) => {
      const count = channelCounts[ch];
      const isActive = activeChannelFilter === ch;
      html += `
        <button type="button" class="channel-chip ${isActive ? "active" : ""}" data-channel="${ch.replace(/"/g, '&quot;')}">
          📺 ${ch} (${count})
        </button>
      `;
    });

    channelChipsContainer.innerHTML = html;

    channelChipsContainer.querySelectorAll(".channel-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        activeChannelFilter = chip.dataset.channel;
        renderChannelFilterChips();
        renderGalleryView();
      });
    });
  }

  function renderGalleryView() {
    if (!dashboardGalleryGrid) return;

    let itemsToDisplay = rawGalleryItems;
    if (activeChannelFilter !== "ALL") {
      itemsToDisplay = rawGalleryItems.filter((item) => (item.channel || "YouTube Channel") === activeChannelFilter);
    }

    if (!itemsToDisplay || itemsToDisplay.length === 0) {
      dashboardGalleryGrid.innerHTML = `
        <div class="empty-gallery-card">
          <div class="empty-icon">✂️</div>
          <h4>No Video Projects Found</h4>
          <p>No video projects match the selected filter. Select <strong>All Channels</strong> or paste a new YouTube link above.</p>
        </div>
      `;
      return;
    }

    dashboardGalleryGrid.innerHTML = "";

    if (galleryGroupBy === "video") {
      // Standard Flat List grouped by Video Projects
      itemsToDisplay.forEach((item) => {
        dashboardGalleryGrid.appendChild(createProjectCardElement(item));
      });
    } else {
      // Grouped by YouTube Channel Sections
      const groups = {};
      itemsToDisplay.forEach((item) => {
        const ch = (item.channel || "YouTube Channel").trim();
        if (!groups[ch]) groups[ch] = [];
        groups[ch].push(item);
      });

      Object.keys(groups).sort().forEach((channelName) => {
        const channelItems = groups[channelName];
        const totalChannelClips = channelItems.reduce((sum, it) => sum + (it.clips ? it.clips.length : 0), 0);

        const groupCard = document.createElement("div");
        groupCard.className = "channel-group-card";

        groupCard.innerHTML = `
          <div class="channel-group-header">
            <div class="channel-group-identity">
              <div class="channel-group-avatar">📺</div>
              <div class="channel-group-info">
                <h4>${channelName}</h4>
                <span>${channelItems.length} ${channelItems.length === 1 ? "Video Project" : "Video Projects"} • ${totalChannelClips} Total Clips</span>
              </div>
            </div>
            <div class="channel-group-actions">
              <button class="btn btn-secondary btn-sm btn-collapse-channel">▲ Hide Channel (${channelItems.length})</button>
            </div>
          </div>
          <div class="channel-group-body"></div>
        `;

        const bodyEl = groupCard.querySelector(".channel-group-body");
        channelItems.forEach((item) => {
          bodyEl.appendChild(createProjectCardElement(item));
        });

        // Channel collapse/expand toggle
        const collapseBtn = groupCard.querySelector(".btn-collapse-channel");
        if (collapseBtn) {
          collapseBtn.addEventListener("click", () => {
            const isOpen = bodyEl.style.display !== "none";
            bodyEl.style.display = isOpen ? "none" : "flex";
            collapseBtn.textContent = isOpen ? `▼ Show Channel (${channelItems.length})` : `▲ Hide Channel (${channelItems.length})`;
          });
        }

        dashboardGalleryGrid.appendChild(groupCard);
      });
    }
  }

  function createProjectCardElement(item) {
    const projectCard = document.createElement("div");
    projectCard.className = "project-card";
    const clips = item.clips || [];
    const isExpanded = expandedProjects.has(item.folder_name);
    const thumbSrc = item.thumbnail || `https://img.youtube.com/vi/${item.video_id}/hqdefault.jpg`;

    projectCard.innerHTML = `
      <div class="project-card-header">
        <div class="project-thumb-box">
          <img src="${thumbSrc}" alt="${item.title || "Video"}" class="project-thumb-img" onerror="this.src='/static/img/fallback.jpg'">
        </div>
        <div class="project-info-main">
          <h4>${item.title || item.folder_name}</h4>
          <div class="project-meta-details">
            <span>👤 ${item.channel || "YouTube Channel"}</span>
            <span>📅 ${item.created_at || "Recent"}</span>
            <span>📁 output/${item.folder_name}</span>
          </div>
          <div class="project-badges">
            <span class="badge badge-primary">🎬 ${clips.length} ${clips.length === 1 ? "Clip" : "Clips"}</span>
          </div>
        </div>
        <div class="project-header-actions">
          <button class="btn btn-primary btn-sm btn-toggle-clips" data-folder="${item.folder_name}">
            ${isExpanded ? "▲ Hide Clips" : "▼ View Clips (" + clips.length + ")"}
          </button>
          <button class="btn btn-secondary btn-sm btn-reclip" data-url="${item.url || `https://www.youtube.com/watch?v=${item.video_id}`}">
            ✂️ Re-Clip Video
          </button>
          <button class="btn btn-outline btn-sm btn-open-project-folder" data-path="${item.folder_path}">
            📂 Open Folder
          </button>
        </div>
      </div>

      <div class="project-clips-wrapper" id="clips-wrap-${item.folder_name}" style="display: ${isExpanded ? "block" : "none"};">
        <div class="project-clips-heading">
          <span>Project Generated Clips (${clips.length})</span>
          <button class="btn btn-secondary btn-sm btn-open-project-folder" data-path="${item.folder_path}">
            📂 Open Explorer Folder
          </button>
        </div>
        <div class="clips-grid">
          ${clips
            .map((clip) => {
              const clipRatio = clip.aspect_ratio || item.aspect_ratio || "9:16";
              const ratioClass =
                clipRatio === "16:9"
                  ? "ratio-16-9"
                  : clipRatio === "1:1"
                  ? "ratio-1-1"
                  : clipRatio === "4:5"
                  ? "ratio-4-5"
                  : "";
              const clipRes = clip.resolution || item.resolution || "1080p";
              const clipFF = clip.face_follow !== undefined ? clip.face_follow : item.face_follow;
              let itemFFBadge = "";
              if (clipFF === "dynamic") {
                itemFFBadge = '<span class="badge badge-overlay">🔄 Dynamic Pan</span>';
              } else if (clipFF === "split") {
                itemFFBadge = '<span class="badge badge-overlay">👥 Dual Podcast</span>';
              } else if (clipFF === "single" || clipFF === true) {
                itemFFBadge = '<span class="badge badge-overlay">👤 Single Speaker</span>';
              }

              return `
              <div class="clip-card">
                <div class="clip-media-container">
                  <video class="clip-video-player ${ratioClass}" controls preload="metadata" playsinline>
                    <source src="${clip.relative_url}" type="video/mp4">
                  </video>
                  <div class="clip-overlay-badges">
                    <span class="badge badge-blue badge-overlay">📱 ${clipRatio}</span>
                    <span class="badge badge-overlay">📺 ${clipRes}</span>
                    ${itemFFBadge}
                  </div>
                </div>
                <div class="clip-card-body">
                  <div class="clip-title">${clip.title}</div>
                  <div class="clip-meta-row">
                    <span>⏱️ ${clip.duration_formatted || "00:30"}</span>
                    <span>💾 ${clip.size_mb} MB</span>
                    <span>${clip.has_srt ? "💬 Captions" : "🔇 Clean"}</span>
                  </div>
                  <div class="clip-actions">
                    <button class="btn btn-publish btn-sm btn-open-publish" 
                      data-path="${clip.file_path}" 
                      data-title="${clip.title.replace(/"/g, '&quot;')}"
                      title="One-Click Publish to YouTube, TikTok, Instagram">
                      🚀 Publish
                    </button>
                    <a href="${clip.relative_url}" download="${clip.filename}" class="btn btn-primary btn-sm">
                      ⬇️ MP4
                    </a>
                    ${
                      clip.has_srt
                        ? `<a href="${clip.srt_url}" download class="btn btn-secondary btn-sm" title="Download Subtitle SRT">📄 SRT</a>`
                        : ""
                    }
                  </div>
                </div>
              </div>
            `;
            })
            .join("")}
        </div>
      </div>
    `;

    // Event handlers for project card
    const toggleBtn = projectCard.querySelector(".btn-toggle-clips");
    const clipsWrap = projectCard.querySelector(`#clips-wrap-${item.folder_name}`);
    toggleBtn.addEventListener("click", () => {
      const currentlyOpen = clipsWrap.style.display !== "none";
      if (currentlyOpen) {
        clipsWrap.style.display = "none";
        toggleBtn.textContent = `▼ View Clips (${clips.length})`;
        expandedProjects.delete(item.folder_name);
      } else {
        clipsWrap.style.display = "block";
        toggleBtn.textContent = "▲ Hide Clips";
        expandedProjects.add(item.folder_name);
      }
    });

    // Video playback overlay fade handling for each clip
    projectCard.querySelectorAll(".clip-card").forEach((clipCard) => {
      const vid = clipCard.querySelector("video");
      const container = clipCard.querySelector(".clip-media-container");
      if (vid && container) {
        vid.addEventListener("play", () => container.classList.add("is-playing"));
        vid.addEventListener("pause", () => container.classList.remove("is-playing"));
        vid.addEventListener("ended", () => container.classList.remove("is-playing"));
      }
    });

    projectCard.querySelector(".btn-reclip").addEventListener("click", (e) => {
      const targetUrl = e.currentTarget.dataset.url;
      window.scrollTo({ top: 0, behavior: "smooth" });
      fetchVideoInfo(targetUrl);
    });

    projectCard.querySelectorAll(".btn-open-project-folder").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        openFolderOnOS({ folder_path: e.currentTarget.dataset.path });
      });
    });

    projectCard.querySelectorAll(".btn-open-publish").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        openPublishModal({
          file_path: e.currentTarget.dataset.path,
          title: e.currentTarget.dataset.title,
        });
      });
    });

    return projectCard;
  }

  // Open Folder Handlers
  if (btnOpenResultFolder) {
    btnOpenResultFolder.addEventListener("click", () => {
      if (lastFolderPath) openFolderOnOS({ folder_path: lastFolderPath });
    });
  }

  async function openFolderOnOS(payload) {
    try {
      await fetch("/api/open-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch (e) {
      console.warn("Folder open err", e);
    }
  }

  // ==========================================================
  // 6. ONE-CLICK SOCIAL PUBLISHING LOGIC
  // ==========================================================
  function openPublishModal(clip) {
    currentPublishClip = clip;
    if (publishTitleInput) publishTitleInput.value = clip.title || "Viral Clip";
    if (publishDescInput) publishDescInput.value = "";
    if (publishLiveFeedback) {
      publishLiveFeedback.style.display = "none";
      publishLiveFeedback.innerHTML = "";
    }
    if (publishLiveLoader) publishLiveLoader.style.display = "none";
    if (publishModal) publishModal.classList.add("active");
  }

  function closePublishModal() {
    if (publishModal) publishModal.classList.remove("active");
    if (activePublishPollInterval) {
      clearInterval(activePublishPollInterval);
      activePublishPollInterval = null;
    }
    if (publishBtnText) publishBtnText.textContent = "🚀 Publish to Selected Socials";
    if (publishSpinner) publishSpinner.style.display = "none";
    if (publishLiveLoader) publishLiveLoader.style.display = "none";
    if (btnStartPublish) btnStartPublish.disabled = false;
  }

  if (btnClosePublish) btnClosePublish.addEventListener("click", closePublishModal);
  if (btnCancelPublish) btnCancelPublish.addEventListener("click", closePublishModal);

  // Platform selection buttons
  if (btnSelectAllPlatforms) {
    btnSelectAllPlatforms.addEventListener("click", () => {
      document.querySelectorAll(".plat-checkbox").forEach((cb) => (cb.checked = true));
      updatePlatformCardStyles();
    });
  }

  if (btnClearPlatforms) {
    btnClearPlatforms.addEventListener("click", () => {
      document.querySelectorAll(".plat-checkbox").forEach((cb) => (cb.checked = false));
      updatePlatformCardStyles();
    });
  }

  document.querySelectorAll(".plat-checkbox").forEach((cb) => {
    cb.addEventListener("change", updatePlatformCardStyles);
  });

  function updatePlatformCardStyles() {
    document.querySelectorAll(".social-checkbox-card").forEach((card) => {
      const cb = card.querySelector(".plat-checkbox");
      if (cb && cb.checked) {
        card.classList.add("selected");
      } else {
        card.classList.remove("selected");
      }
    });
  }
  updatePlatformCardStyles();

  // Hashtag chips handler
  document.querySelectorAll(".tag-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const tag = chip.dataset.tag;
      if (publishTitleInput && !publishTitleInput.value.includes(tag)) {
        publishTitleInput.value = `${publishTitleInput.value.trim()} ${tag}`.trim();
      }
    });
  });

  // Execute One-Click Publish
  if (btnStartPublish) {
    btnStartPublish.addEventListener("click", async () => {
      if (!currentPublishClip || !currentPublishClip.file_path) {
        alert("No video clip selected for publishing.");
        return;
      }

      const selectedPlatforms = [];
      const cbYt = document.getElementById("plat-youtube");
      const cbTt = document.getElementById("plat-tiktok");
      const cbIg = document.getElementById("plat-instagram");

      if (cbYt && cbYt.checked) selectedPlatforms.push("youtube");
      if (cbTt && cbTt.checked) selectedPlatforms.push("tiktok");
      if (cbIg && cbIg.checked) selectedPlatforms.push("instagram");

      if (selectedPlatforms.length === 0) {
        alert("Please select at least one social media platform to publish to.");
        return;
      }

      const title = (publishTitleInput ? publishTitleInput.value.trim() : "") || "New Clip";
      const description = publishDescInput ? publishDescInput.value.trim() : "";
      const ytPrivacyEl = document.getElementById("opt-yt-privacy");
      const ttPrivacyEl = document.getElementById("opt-tt-privacy");
      const ytPrivacy = ytPrivacyEl ? ytPrivacyEl.value : "public";
      const ttPrivacy = ttPrivacyEl ? ttPrivacyEl.value : "PUBLIC_TO_EVERYONE";

      const payload = {
        file_path: currentPublishClip.file_path,
        title: title,
        description: description,
        platforms: selectedPlatforms,
        options: {
          youtube_privacy: ytPrivacy,
          tiktok_privacy: ttPrivacy,
          instagram_share_feed: true,
        },
      };

      if (publishBtnText) publishBtnText.textContent = "Publishing...";
      if (publishSpinner) publishSpinner.style.display = "inline";
      btnStartPublish.disabled = true;

      // Show Animated Loader Banner
      if (publishLiveLoader) publishLiveLoader.style.display = "flex";

      // Show feedback box
      if (publishLiveFeedback) {
        publishLiveFeedback.style.display = "flex";
        publishLiveFeedback.innerHTML = `
          <div style="font-weight: 700; font-size: 0.85rem; color: #fff; margin-bottom: 4px;">🚀 Uploading to Selected Platforms:</div>
          ${selectedPlatforms
            .map(
              (p) => `
            <div class="platform-status-row" id="feed-row-${p}">
              <span style="text-transform: capitalize; font-weight: 600;">${p === "youtube" ? "▶ YouTube Shorts" : p === "tiktok" ? "🎵 TikTok" : "📸 Instagram Reels"}:</span>
              <span id="feed-status-${p}" style="color: var(--primary);">⏳ Uploading in background...</span>
            </div>
          `
            )
            .join("")}
        `;
      }

      // Smooth scroll modal to bottom to keep feedback in view
      const modalBox = publishModal.querySelector(".loader-modal-content");
      if (modalBox) modalBox.scrollTo({ top: modalBox.scrollHeight, behavior: "smooth" });

      try {
        const res = await fetch("/api/social/publish", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to initiate publishing.");

        trackPublishJob(data.job_id);
      } catch (err) {
        alert(`Publish error: ${err.message}`);
        if (publishBtnText) publishBtnText.textContent = "🚀 Publish to Selected Socials";
        if (publishSpinner) publishSpinner.style.display = "none";
        if (publishLiveLoader) publishLiveLoader.style.display = "none";
        btnStartPublish.disabled = false;
      }
    });
  }

  function trackPublishJob(jobId) {
    if (activePublishPollInterval) clearInterval(activePublishPollInterval);

    activePublishPollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/social/publish-status/${jobId}`);
        const data = await res.json();

        if (data.status === "completed" || data.status === "failed" || data.status === "error") {
          clearInterval(activePublishPollInterval);
          activePublishPollInterval = null;

          if (publishBtnText) publishBtnText.textContent = "🚀 Publish to Selected Socials";
          if (publishSpinner) publishSpinner.style.display = "none";
          if (publishLiveLoader) publishLiveLoader.style.display = "none";
          if (btnStartPublish) btnStartPublish.disabled = false;

          const results = data.results || {};
          Object.keys(results).forEach((platform) => {
            const pRes = results[platform];
            const statusEl = document.getElementById(`feed-status-${platform}`);
            if (statusEl) {
              if (pRes.success) {
                if (pRes.url) {
                  statusEl.innerHTML = `✅ <a href="${pRes.url}" target="_blank" style="color: var(--primary); text-decoration: underline; font-weight:700;">Published! Open Video</a>`;
                } else {
                  statusEl.innerHTML = `✅ <span style="color: var(--primary); font-weight:700;">${pRes.message || "Published successfully!"}</span>`;
                }
              } else {
                statusEl.innerHTML = `❌ <span style="color: var(--accent-red);" title="${pRes.error}">${pRes.error ? pRes.error.substring(0, 45) + '...' : 'Upload failed'}</span>`;
              }
            }
          });
          refreshPostHistory();
        }
      } catch (e) {
        console.warn("Poll error", e);
      }
    }, 1500);
  }

  // ==========================================================
  // 7. SOCIAL ACCOUNTS SETTINGS & AUTH LOGIC
  // ==========================================================
  async function refreshSocialAccounts() {
    try {
      const res = await fetch("/api/social/accounts");
      const data = await res.json();
      if (!data.success) return;

      const accounts = data.accounts || {};
      let connectedCount = 0;

      // Update YouTube UI & Populate saved inputs
      const yt = accounts.youtube || {};
      const bannerYt = document.getElementById("banner-yt");
      const bannerYtIcon = document.getElementById("banner-yt-icon");
      const bannerYtText = document.getElementById("banner-yt-text");
      const statusTagYt = document.getElementById("status-tag-youtube");

      const ytClientIdInput = document.getElementById("yt-client-id");
      const ytClientSecretInput = document.getElementById("yt-client-secret");
      const ytChannelInput = document.getElementById("yt-channel");
      const ytTokenInput = document.getElementById("yt-token");
      const ytRefreshTokenInput = document.getElementById("yt-refresh-token");

      if (yt.client_id && ytClientIdInput) {
        ytClientIdInput.value = yt.client_id;
      }
      if (yt.client_secret && ytClientSecretInput) {
        ytClientSecretInput.value = yt.client_secret;
      }
      if (yt.channel_name && ytChannelInput) {
        ytChannelInput.value = yt.channel_name;
      }
      if (yt.access_token && ytTokenInput) {
        ytTokenInput.value = yt.access_token;
      }
      if (yt.refresh_token && ytRefreshTokenInput) {
        ytRefreshTokenInput.value = yt.refresh_token;
      }

      if (yt.connected) {
        connectedCount++;
        if (bannerYt) bannerYt.className = "account-status-banner connected";
        if (bannerYtIcon) bannerYtIcon.textContent = "🟢";
        if (bannerYtText) bannerYtText.textContent = `YouTube: Connected (${yt.account_name || "Active Channel"})`;
        if (statusTagYt) {
          statusTagYt.textContent = "Connected 🟢";
          statusTagYt.style.color = "var(--primary)";
        }
      } else {
        if (bannerYt) bannerYt.className = "account-status-banner";
        if (bannerYtIcon) bannerYtIcon.textContent = "⚪";
        if (bannerYtText) bannerYtText.textContent = "YouTube: Not Configured";
        if (statusTagYt) {
          statusTagYt.textContent = "Not Configured";
          statusTagYt.style.color = "var(--text-muted)";
        }
      }

      // Update TikTok UI & Populate saved inputs
      const tt = accounts.tiktok || {};
      const bannerTt = document.getElementById("banner-tt");
      const bannerTtIcon = document.getElementById("banner-tt-icon");
      const bannerTtText = document.getElementById("banner-tt-text");
      const statusTagTt = document.getElementById("status-tag-tiktok");
      const ttAccountInput = document.getElementById("tt-account");
      const ttTokenInput = document.getElementById("tt-token");
      const ttRefreshTokenInput = document.getElementById("tt-refresh-token");
      const ttClientKeyInput = document.getElementById("tt-client-key");
      const ttClientSecretInput = document.getElementById("tt-client-secret");

      if (tt.account_name && ttAccountInput) {
        ttAccountInput.value = tt.account_name;
      }
      if (tt.client_key && ttClientKeyInput) {
        ttClientKeyInput.value = tt.client_key;
      }
      if (tt.client_secret && ttClientSecretInput) {
        ttClientSecretInput.value = tt.client_secret;
      }
      if (tt.access_token && ttTokenInput) {
        ttTokenInput.value = tt.access_token;
      }
      if (tt.refresh_token && ttRefreshTokenInput) {
        ttRefreshTokenInput.value = tt.refresh_token;
      }

      if (tt.connected) {
        connectedCount++;
        if (bannerTt) bannerTt.className = "account-status-banner connected";
        if (bannerTtIcon) bannerTtIcon.textContent = "🟢";
        if (bannerTtText) bannerTtText.textContent = `TikTok: Connected (${tt.account_name || "Active Profile"})`;
        if (statusTagTt) {
          statusTagTt.textContent = "Connected 🟢";
          statusTagTt.style.color = "var(--primary)";
        }
      } else {
        if (bannerTt) bannerTt.className = "account-status-banner";
        if (bannerTtIcon) bannerTtIcon.textContent = "⚪";
        if (bannerTtText) bannerTtText.textContent = "TikTok: Not Configured";
        if (statusTagTt) {
          statusTagTt.textContent = "Not Configured";
          statusTagTt.style.color = "var(--text-muted)";
        }
      }

      // Update Instagram UI & Populate saved inputs
      const ig = accounts.instagram || {};
      const bannerIg = document.getElementById("banner-ig");
      const bannerIgIcon = document.getElementById("banner-ig-icon");
      const bannerIgText = document.getElementById("banner-ig-text");
      const statusTagIg = document.getElementById("status-tag-instagram");
      const igAccountIdInput = document.getElementById("ig-account-id");
      const igTokenInput = document.getElementById("ig-token");
      const igAppIdInput = document.getElementById("ig-app-id");
      const igAppSecretInput = document.getElementById("ig-app-secret");

      if (ig.instagram_account_id && igAccountIdInput) {
        igAccountIdInput.value = ig.instagram_account_id;
      }
      if (ig.app_id && igAppIdInput) {
        igAppIdInput.value = ig.app_id;
      }
      if (ig.app_secret && igAppSecretInput) {
        igAppSecretInput.value = ig.app_secret;
      }
      if (ig.access_token && igTokenInput) {
        igTokenInput.value = ig.access_token;
      }

      if (ig.connected) {
        connectedCount++;
        if (bannerIg) bannerIg.className = "account-status-banner connected";
        if (bannerIgIcon) bannerIgIcon.textContent = "🟢";
        if (bannerIgText) bannerIgText.textContent = `Instagram: Connected (${ig.account_name || "Business Account"})`;
        if (statusTagIg) {
          statusTagIg.textContent = "Connected 🟢";
          statusTagIg.style.color = "var(--primary)";
        }
      } else {
        if (bannerIg) bannerIg.className = "account-status-banner";
        if (bannerIgIcon) bannerIgIcon.textContent = "⚪";
        if (bannerIgText) bannerIgText.textContent = "Instagram: Not Configured";
        if (statusTagIg) {
          statusTagIg.textContent = "Not Configured";
          statusTagIg.style.color = "var(--text-muted)";
        }
      }

      if (connectedPlatformsCount) connectedPlatformsCount.textContent = `${connectedCount}/3`;
    } catch (err) {
      console.warn("Failed to load social accounts:", err);
    }
  }

  // Open & Close Social Accounts Modal
  if (btnOpenSocialModal) {
    btnOpenSocialModal.addEventListener("click", () => {
      if (socialModal) socialModal.classList.add("active");
      refreshSocialAccounts();
    });
  }

  if (btnCloseSocialModal) {
    btnCloseSocialModal.addEventListener("click", () => {
      if (socialModal) socialModal.classList.remove("active");
    });
  }

  // Tab Navigation in Social Modal
  document.querySelectorAll(".social-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".social-tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".social-tab-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const targetPane = document.getElementById(btn.dataset.tab);
      if (targetPane) targetPane.classList.add("active");
    });
  });

  // Save YouTube Auth
  const btnSaveYt = document.getElementById("btn-save-yt");
  if (btnSaveYt) {
    btnSaveYt.addEventListener("click", async () => {
      const token = document.getElementById("yt-token").value.trim();
      const refreshToken = document.getElementById("yt-refresh-token").value.trim();
      const clientId = document.getElementById("yt-client-id").value.trim();
      const clientSecret = document.getElementById("yt-client-secret").value.trim();
      const channel = document.getElementById("yt-channel").value.trim();

      if (!token && !refreshToken) return alert("Please enter a YouTube Access Token or Refresh Token.");

      try {
        const res = await fetch("/api/social/accounts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            platform: "youtube",
            credentials: {
              access_token: token,
              refresh_token: refreshToken,
              client_id: clientId,
              client_secret: clientSecret,
              channel_name: channel,
            },
          }),
        });
        const data = await res.json();
        if (data.success) {
          alert("YouTube Auth Saved Successfully!");
          refreshSocialAccounts();
        }
      } catch (e) {
        alert("Error saving YouTube credentials: " + e.message);
      }
    });
  }

  // Refresh YouTube Token
  const btnRefreshYt = document.getElementById("btn-refresh-yt");
  if (btnRefreshYt) {
    btnRefreshYt.addEventListener("click", async () => {
      try {
        btnRefreshYt.textContent = "⏳ Renewing...";
        const res = await fetch("/api/social/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ platform: "youtube" }),
        });
        const data = await res.json();
        alert(data.message);
        refreshSocialAccounts();
      } catch (e) {
        alert("Error refreshing YouTube token: " + e.message);
      } finally {
        btnRefreshYt.textContent = "🔄 Refresh Token";
      }
    });
  }

  // Test YouTube Auth
  const btnTestYt = document.getElementById("btn-test-yt");
  if (btnTestYt) {
    btnTestYt.addEventListener("click", async () => {
      const token = document.getElementById("yt-token").value.trim();
      try {
        const res = await fetch("/api/social/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ platform: "youtube", token: token || undefined }),
        });
        const data = await res.json();
        alert(data.message || (data.success ? "YouTube Connection Successful!" : "YouTube Auth Failed"));
        refreshSocialAccounts();
      } catch (e) {
        alert("Error testing connection: " + e.message);
      }
    });
  }

  // Save TikTok Auth
  const btnSaveTt = document.getElementById("btn-save-tt");
  if (btnSaveTt) {
    btnSaveTt.addEventListener("click", async () => {
      const token = document.getElementById("tt-token").value.trim();
      const refreshToken = document.getElementById("tt-refresh-token").value.trim();
      const clientKey = document.getElementById("tt-client-key").value.trim();
      const clientSecret = document.getElementById("tt-client-secret").value.trim();
      const handle = document.getElementById("tt-account").value.trim();

      if (!token && !refreshToken) return alert("Please enter a TikTok Access Token or Refresh Token.");

      try {
        const res = await fetch("/api/social/accounts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            platform: "tiktok",
            credentials: {
              access_token: token,
              refresh_token: refreshToken,
              client_key: clientKey,
              client_secret: clientSecret,
              account_name: handle,
            },
          }),
        });
        const data = await res.json();
        if (data.success) {
          alert("TikTok Auth Saved Successfully!");
          refreshSocialAccounts();
        }
      } catch (e) {
        alert("Error saving TikTok credentials: " + e.message);
      }
    });
  }

  // Refresh TikTok Token
  const btnRefreshTt = document.getElementById("btn-refresh-tt");
  if (btnRefreshTt) {
    btnRefreshTt.addEventListener("click", async () => {
      try {
        btnRefreshTt.textContent = "⏳ Renewing...";
        const res = await fetch("/api/social/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ platform: "tiktok" }),
        });
        const data = await res.json();
        alert(data.message);
        refreshSocialAccounts();
      } catch (e) {
        alert("Error refreshing TikTok token: " + e.message);
      } finally {
        btnRefreshTt.textContent = "🔄 Refresh Token";
      }
    });
  }

  // Test TikTok Auth
  const btnTestTt = document.getElementById("btn-test-tt");
  if (btnTestTt) {
    btnTestTt.addEventListener("click", async () => {
      const token = document.getElementById("tt-token").value.trim();
      try {
        const res = await fetch("/api/social/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ platform: "tiktok", token: token || undefined }),
        });
        const data = await res.json();
        alert(data.message || (data.success ? "TikTok Connection Successful!" : "TikTok Auth Failed"));
        refreshSocialAccounts();
      } catch (e) {
        alert("Error testing connection: " + e.message);
      }
    });
  }

  // Save Instagram Auth
  const btnSaveIg = document.getElementById("btn-save-ig");
  if (btnSaveIg) {
    btnSaveIg.addEventListener("click", async () => {
      const token = document.getElementById("ig-token").value.trim();
      const appId = document.getElementById("ig-app-id").value.trim();
      const appSecret = document.getElementById("ig-app-secret").value.trim();
      const accountId = document.getElementById("ig-account-id").value.trim();
      if (!token || !accountId) return alert("Please enter both Instagram Access Token and Business Account ID.");

      try {
        const res = await fetch("/api/social/accounts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            platform: "instagram",
            credentials: {
              access_token: token,
              app_id: appId,
              app_secret: appSecret,
              instagram_account_id: accountId,
            },
          }),
        });
        const data = await res.json();
        if (data.success) {
          alert("Instagram Auth Saved Successfully!");
          refreshSocialAccounts();
        }
      } catch (e) {
        alert("Error saving Instagram credentials: " + e.message);
      }
    });
  }

  // Refresh Instagram Token
  const btnRefreshIg = document.getElementById("btn-refresh-ig");
  if (btnRefreshIg) {
    btnRefreshIg.addEventListener("click", async () => {
      try {
        btnRefreshIg.textContent = "⏳ Renewing...";
        const res = await fetch("/api/social/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ platform: "instagram" }),
        });
        const data = await res.json();
        alert(data.message);
        refreshSocialAccounts();
      } catch (e) {
        alert("Error refreshing Instagram token: " + e.message);
      } finally {
        btnRefreshIg.textContent = "🔄 Refresh Token";
      }
    });
  }

  // Test Instagram Auth
  const btnTestIg = document.getElementById("btn-test-ig");
  if (btnTestIg) {
    btnTestIg.addEventListener("click", async () => {
      const token = document.getElementById("ig-token").value.trim();
      try {
        const res = await fetch("/api/social/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ platform: "instagram", token: token || undefined }),
        });
        const data = await res.json();
        alert(data.message || (data.success ? "Instagram Connection Successful!" : "Instagram Auth Failed"));
        refreshSocialAccounts();
      } catch (e) {
        alert("Error testing connection: " + e.message);
      }
    });
  }

  // ==========================================================
  // 8. POST PUBLISHING HISTORY LOGIC
  // ==========================================================
  async function refreshPostHistory() {
    try {
      const res = await fetch("/api/social/history");
      const data = await res.json();
      if (!data.success) return;

      const history = data.history || [];
      if (historyCountBadge) historyCountBadge.textContent = history.length;

      renderHistoryList(history);
    } catch (e) {
      console.warn("Failed to load post history:", e);
    }
  }

  function renderHistoryList(history) {
    if (!historyItemsContainer) return;

    if (!history || history.length === 0) {
      historyItemsContainer.innerHTML = `
        <div style="text-align:center; padding: 40px 20px; color: var(--text-muted);">
          <div style="font-size: 2.5rem; margin-bottom: 8px;">📜</div>
          <h4>No Post History Yet</h4>
          <p style="font-size: 0.85rem; margin-top: 4px;">Published video clips will be permanently recorded here with direct video links.</p>
        </div>
      `;
      return;
    }

    historyItemsContainer.innerHTML = "";

    history.forEach((item) => {
      const row = document.createElement("div");
      row.className = "history-item-row";

      const results = item.results || {};
      const chipsHtml = Object.keys(results)
        .map((plat) => {
          const res = results[plat];
          const icon = plat === "youtube" ? "▶" : plat === "tiktok" ? "🎵" : "📸";
          const platName = plat === "youtube" ? "YouTube Shorts" : plat === "tiktok" ? "TikTok" : "Instagram Reels";

          if (res.success) {
            if (res.url) {
              return `<a href="${res.url}" target="_blank" class="history-link-chip" title="Open live published video">${icon} ${platName}: Watch ↗</a>`;
            } else {
              return `<span class="history-link-chip">${icon} ${platName}: Published ✅</span>`;
            }
          } else {
            return `<span class="history-link-chip failed" title="${res.error || 'Failed'}">${icon} ${platName}: Failed ✕</span>`;
          }
        })
        .join("");

      row.innerHTML = `
        <div class="history-item-top">
          <div>
            <div class="history-item-title">${item.title}</div>
            <div class="history-item-meta">
              <span>📅 ${item.timestamp}</span>
              <span>📁 ${item.filename}</span>
              <span class="badge ${item.success ? "badge-primary" : ""}">${item.success ? "✅ Completed" : "⚠️ Failed"}</span>
            </div>
          </div>
          <button class="btn btn-outline btn-sm btn-del-history" data-id="${item.id}" title="Delete this history record" style="color: var(--accent-red); border-color: rgba(255,0,0,0.2);">
            🗑️
          </button>
        </div>
        <div class="history-results-list">
          ${chipsHtml || '<span style="font-size:0.75rem; color:var(--text-muted);">No platform details</span>'}
        </div>
      `;

      row.querySelector(".btn-del-history").addEventListener("click", async (e) => {
        const id = e.currentTarget.dataset.id;
        try {
          await fetch(`/api/social/history/${id}`, { method: "DELETE" });
          refreshPostHistory();
        } catch (err) {
          console.error(err);
        }
      });

      historyItemsContainer.appendChild(row);
    });
  }

  if (btnOpenHistoryModal) {
    btnOpenHistoryModal.addEventListener("click", () => {
      if (historyModal) historyModal.classList.add("active");
      refreshPostHistory();
    });
  }

  if (btnCloseHistory) {
    btnCloseHistory.addEventListener("click", () => {
      if (historyModal) historyModal.classList.remove("active");
    });
  }

  if (btnClearHistory) {
    btnClearHistory.addEventListener("click", async () => {
      if (confirm("Are you sure you want to clear all post history?")) {
        try {
          await fetch("/api/social/history", { method: "DELETE" });
          refreshPostHistory();
        } catch (e) {
          console.error(e);
        }
      }
    });
  }

  // ==========================================================
  // 9. AUTO-PILOT STUDIO CONTROLLER
  // ==========================================================
  // Mode switcher elements
  const btnModeManual = document.getElementById("btn-mode-manual");
  const btnModeAutopilot = document.getElementById("btn-mode-autopilot");
  const manualClipperMode = document.getElementById("manual-clipper-mode");
  const autopilotMode = document.getElementById("autopilot-mode");
  const headerApDot = document.getElementById("header-ap-dot");

  // Auto-Pilot master elements
  const apEnableToggle = document.getElementById("ap-enable-toggle");
  const apStatusPill = document.getElementById("ap-status-pill");
  const apStatusText = document.getElementById("ap-status-text");
  const apScheduleInfo = document.getElementById("ap-schedule-info");
  const apToggleHint = document.getElementById("ap-toggle-hint");
  const btnSaveAutopilot = document.getElementById("btn-save-autopilot");
  const btnTriggerAutopilot = document.getElementById("btn-trigger-autopilot");
  const apTriggerText = document.getElementById("ap-trigger-text");
  const apTriggerSpinner = document.getElementById("ap-trigger-spinner");

  // Auto-Pilot live progress banner
  const apLiveBanner = document.getElementById("ap-live-banner");
  const apLiveTitle = document.getElementById("ap-live-title");
  const apLivePct = document.getElementById("ap-live-pct");
  const apLiveProgressFill = document.getElementById("ap-live-progress-fill");
  const apLiveMsg = document.getElementById("ap-live-msg");

  // Auto-Pilot form controls
  const apTimeInput = document.getElementById("ap-time-input");
  const apCategorySelect = document.getElementById("ap-category-select");
  const apMaxVideosSlider = document.getElementById("ap-max-videos-slider");
  const apMaxVideosVal = document.getElementById("ap-max-videos-val");
  const apCountryChipsContainer = document.getElementById("ap-country-chips-container");
  const apSelectedCountriesCount = document.getElementById("ap-selected-countries-count");
  const btnCountryAll = document.getElementById("btn-country-all");
  const btnCountryTop3 = document.getElementById("btn-country-top3");
  const btnCountryClear = document.getElementById("btn-country-clear");

  const apClipCountSlider = document.getElementById("ap-clip-count-slider");
  const apClipCountVal = document.getElementById("ap-clip-count-val");
  const apDurationSlider = document.getElementById("ap-duration-slider");
  const apDurationVal = document.getElementById("ap-duration-val");

  const apTargetYt = document.getElementById("ap-target-yt");
  const apTargetTt = document.getElementById("ap-target-tt");
  const apTargetIg = document.getElementById("ap-target-ig");
  const apPrivacySelect = document.getElementById("ap-privacy-select");
  const apTitleTemplate = document.getElementById("ap-title-template");
  const apDescTemplate = document.getElementById("ap-desc-template");

  // Auto-Pilot history
  const apHistoryTableWrapper = document.getElementById("ap-history-table-wrapper");
  const btnClearApHistory = document.getElementById("btn-clear-ap-history");

  // Auto-Pilot Local State
  let apSelectedCountries = new Set(["US", "ID"]);
  let apSupportedCountries = [];
  let apSelectedRatio = "9:16";
  let apSelectedSubtitle = "tiktok";
  let apSelectedFace = "single";
  let apSelectedRes = "1080p";
  let apStatusPollInterval = null;

  // 1. Mode Switcher
  if (btnModeManual && btnModeAutopilot) {
    btnModeManual.addEventListener("click", () => {
      btnModeManual.classList.add("active");
      btnModeAutopilot.classList.remove("active");
      if (manualClipperMode) manualClipperMode.style.display = "block";
      if (autopilotMode) autopilotMode.style.display = "none";
    });

    btnModeAutopilot.addEventListener("click", () => {
      btnModeAutopilot.classList.add("active");
      btnModeManual.classList.remove("active");
      if (manualClipperMode) manualClipperMode.style.display = "none";
      if (autopilotMode) autopilotMode.style.display = "block";
      loadAutopilotConfigAndStatus();
      loadAutopilotHistory();
    });
  }

  // 2. Sliders setup for Auto-Pilot
  if (apMaxVideosSlider) {
    apMaxVideosSlider.addEventListener("input", (e) => {
      if (apMaxVideosVal) apMaxVideosVal.textContent = `${e.target.value} ${e.target.value == 1 ? "Video" : "Videos"}`;
    });
  }

  if (apClipCountSlider) {
    apClipCountSlider.addEventListener("input", (e) => {
      if (apClipCountVal) apClipCountVal.textContent = `${e.target.value} ${e.target.value == 1 ? "Clip" : "Clips"}`;
    });
  }

  if (apDurationSlider) {
    apDurationSlider.addEventListener("input", (e) => {
      if (apDurationVal) apDurationVal.textContent = `${e.target.value}s`;
    });
  }

  setupOptionGroup("ap-ratio-options", (val) => (apSelectedRatio = val));
  setupOptionGroup("ap-sub-options", (val) => (apSelectedSubtitle = val));
  setupOptionGroup("ap-face-options", (val) => (apSelectedFace = val));
  setupOptionGroup("ap-res-options", (val) => (apSelectedRes = val));

  function setOptionGroupActive(groupId, activeValue) {
    const container = document.getElementById(groupId);
    if (!container) return;
    const cards = container.querySelectorAll(".option-card");
    cards.forEach((card) => {
      if (card.dataset.value === activeValue) {
        card.classList.add("active");
      } else {
        card.classList.remove("active");
      }
    });
  }

  // 3. Country Chips & Shortcuts
  function renderCountryChips() {
    if (!apCountryChipsContainer) return;
    apCountryChipsContainer.innerHTML = "";

    apSupportedCountries.forEach((c) => {
      const isSelected = apSelectedCountries.has(c.code);
      const chip = document.createElement("div");
      chip.className = `ap-country-chip ${isSelected ? "active" : ""}`;
      chip.innerHTML = `
        <span class="ap-country-flag">${c.flag}</span>
        <span>${c.name}</span>
      `;
      chip.addEventListener("click", () => {
        if (apSelectedCountries.has(c.code)) {
          if (apSelectedCountries.size > 1) {
            apSelectedCountries.delete(c.code);
          } else {
            alert("At least one target country must remain selected.");
          }
        } else {
          apSelectedCountries.add(c.code);
        }
        renderCountryChips();
      });
      apCountryChipsContainer.appendChild(chip);
    });

    if (apSelectedCountriesCount) {
      apSelectedCountriesCount.textContent = `${apSelectedCountries.size} Selected`;
    }
  }

  if (btnCountryAll) {
    btnCountryAll.addEventListener("click", () => {
      apSupportedCountries.forEach((c) => apSelectedCountries.add(c.code));
      renderCountryChips();
    });
  }

  if (btnCountryTop3) {
    btnCountryTop3.addEventListener("click", () => {
      apSelectedCountries = new Set(["US", "ID", "GB"]);
      renderCountryChips();
    });
  }

  if (btnCountryClear) {
    btnCountryClear.addEventListener("click", () => {
      apSelectedCountries = new Set(["US"]);
      renderCountryChips();
    });
  }

  // 4. Toggle Switch Event
  if (apEnableToggle) {
    apEnableToggle.addEventListener("change", () => {
      const isChecked = apEnableToggle.checked;
      updateStatusBadgeUI(isChecked, apScheduleInfo ? apScheduleInfo.textContent : "");
    });
  }

  function updateStatusBadgeUI(isEnabled, nextRunStr) {
    if (apStatusPill && apStatusText && apToggleHint) {
      if (isEnabled) {
        apStatusPill.className = "ap-status-pill active";
        apStatusText.textContent = "🟢 Auto-Pilot Active";
        apToggleHint.textContent = "ON";
        apToggleHint.className = "ap-toggle-hint active";
        if (headerApDot) {
          headerApDot.className = "status-indicator-dot active";
          headerApDot.title = "Auto-Pilot is Active";
        }
      } else {
        apStatusPill.className = "ap-status-pill inactive";
        apStatusText.textContent = "⚪ Auto-Pilot Inactive";
        apToggleHint.textContent = "OFF";
        apToggleHint.className = "ap-toggle-hint";
        if (headerApDot) {
          headerApDot.className = "status-indicator-dot off";
          headerApDot.title = "Auto-Pilot is Off";
        }
      }
    }
    if (apScheduleInfo && nextRunStr) {
      apScheduleInfo.textContent = isEnabled ? `Next Run: ${nextRunStr}` : "Next Run: Disabled";
    }
  }

  // 5. Load Settings & Scheduler Heartbeat
  async function loadAutopilotConfigAndStatus() {
    try {
      const [cfgRes, statRes] = await Promise.all([
        fetch("/api/autopilot/config"),
        fetch("/api/autopilot/status")
      ]);
      const cfgData = await cfgRes.json();
      const statData = await statRes.json();

      if (!cfgData.success) return;

      apSupportedCountries = cfgData.country_options || [];
      const config = cfgData.config || {};
      const status = statData.status || {};

      // Populate Form Fields
      if (apEnableToggle) apEnableToggle.checked = !!config.enabled;
      if (apTimeInput) apTimeInput.value = config.schedule_time || "09:00";
      if (apCategorySelect) apCategorySelect.value = config.category || "all";

      if (apMaxVideosSlider) {
        apMaxVideosSlider.value = config.max_videos_per_run || 3;
        if (apMaxVideosVal) apMaxVideosVal.textContent = `${apMaxVideosSlider.value} Videos`;
      }

      // Countries
      apSelectedCountries = new Set(config.countries || ["US", "ID"]);
      renderCountryChips();

      // Clip Preferences
      const clipPrefs = config.clip_preferences || {};
      apSelectedRatio = clipPrefs.aspect_ratio || "9:16";
      apSelectedSubtitle = clipPrefs.subtitle_option || "tiktok";
      apSelectedFace = clipPrefs.face_follow || "single";
      apSelectedRes = clipPrefs.resolution || "1080p";

      setOptionGroupActive("ap-ratio-options", apSelectedRatio);
      setOptionGroupActive("ap-sub-options", apSelectedSubtitle);
      setOptionGroupActive("ap-face-options", apSelectedFace);
      setOptionGroupActive("ap-res-options", apSelectedRes);

      if (apClipCountSlider) {
        apClipCountSlider.value = clipPrefs.clip_count || 2;
        if (apClipCountVal) apClipCountVal.textContent = `${apClipCountSlider.value} Clips`;
      }

      if (apDurationSlider) {
        apDurationSlider.value = clipPrefs.target_duration || 30;
        if (apDurationVal) apDurationVal.textContent = `${apDurationSlider.value}s`;
      }

      // Upload Targets
      const uploadTargets = config.upload_targets || {};
      if (apTargetYt) apTargetYt.checked = !!uploadTargets.youtube;
      if (apTargetTt) apTargetTt.checked = !!uploadTargets.tiktok;
      if (apTargetIg) apTargetIg.checked = !!uploadTargets.instagram;

      const pubModeRadio = document.querySelector(`input[name="ap-publish-mode"][value="${config.auto_publish_mode || "auto_upload"}"]`);
      if (pubModeRadio) pubModeRadio.checked = true;

      if (apPrivacySelect) apPrivacySelect.value = config.privacy_status || "public";
      if (apTitleTemplate) apTitleTemplate.value = config.title_template || "{clip_title} #shorts #trending";
      if (apDescTemplate) apDescTemplate.value = config.description_template || "";

      // Update Status Header
      updateStatusBadgeUI(config.enabled, status.next_scheduled_run);

      // Check if job is currently executing
      if (status.is_executing) {
        startAutopilotStatusPolling();
      }
    } catch (err) {
      console.warn("Failed to load Auto-Pilot config:", err);
    }
  }

  // 6. Save Settings
  if (btnSaveAutopilot) {
    btnSaveAutopilot.addEventListener("click", async () => {
      const selectedPubMode = document.querySelector('input[name="ap-publish-mode"]:checked')?.value || "auto_upload";

      const payload = {
        enabled: apEnableToggle ? apEnableToggle.checked : false,
        schedule_time: apTimeInput ? apTimeInput.value : "09:00",
        countries: Array.from(apSelectedCountries),
        category: apCategorySelect ? apCategorySelect.value : "all",
        max_videos_per_run: parseInt(apMaxVideosSlider ? apMaxVideosSlider.value : 3, 10),
        clip_preferences: {
          aspect_ratio: apSelectedRatio,
          resolution: apSelectedRes,
          clip_count: parseInt(apClipCountSlider ? apClipCountSlider.value : 2, 10),
          target_duration: parseFloat(apDurationSlider ? apDurationSlider.value : 30),
          face_follow: apSelectedFace,
          subtitle_option: apSelectedSubtitle,
        },
        upload_targets: {
          youtube: apTargetYt ? apTargetYt.checked : false,
          tiktok: apTargetTt ? apTargetTt.checked : false,
          instagram: apTargetIg ? apTargetIg.checked : false,
        },
        privacy_status: apPrivacySelect ? apPrivacySelect.value : "public",
        auto_publish_mode: selectedPubMode,
        title_template: apTitleTemplate ? apTitleTemplate.value : "{clip_title} #shorts #trending",
        description_template: apDescTemplate ? apDescTemplate.value : "",
      };

      btnSaveAutopilot.disabled = true;
      const origText = btnSaveAutopilot.textContent;
      btnSaveAutopilot.textContent = "Saving...";

      try {
        const res = await fetch("/api/autopilot/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
          throw new Error(data.detail || "Failed to save settings.");
        }

        btnSaveAutopilot.textContent = "✓ Settings Saved!";
        btnSaveAutopilot.style.background = "linear-gradient(135deg, #10B981, #059669)";
        updateStatusBadgeUI(payload.enabled, data.status?.next_scheduled_run);

        setTimeout(() => {
          btnSaveAutopilot.textContent = origText;
          btnSaveAutopilot.style.background = "";
          btnSaveAutopilot.disabled = false;
        }, 2200);
      } catch (err) {
        alert(`Error saving Auto-Pilot settings: ${err.message}`);
        btnSaveAutopilot.textContent = origText;
        btnSaveAutopilot.disabled = false;
      }
    });
  }

  // 7. Manual Run Trigger
  if (btnTriggerAutopilot) {
    btnTriggerAutopilot.addEventListener("click", async () => {
      if (!confirm("Start Auto-Pilot pipeline now? It will scrape trending videos, generate clips, and auto-publish according to your settings.")) {
        return;
      }

      btnTriggerAutopilot.disabled = true;
      if (apTriggerSpinner) apTriggerSpinner.style.display = "inline";
      if (apTriggerText) apTriggerText.textContent = "Starting Pipeline...";

      try {
        const res = await fetch("/api/autopilot/trigger", { method: "POST" });
        const data = await res.json();
        if (!res.ok || !data.success) {
          throw new Error(data.message || data.detail || "Failed to trigger auto-pilot.");
        }

        startAutopilotStatusPolling();
      } catch (err) {
        alert(`Could not start Auto-Pilot: ${err.message}`);
        btnTriggerAutopilot.disabled = false;
        if (apTriggerSpinner) apTriggerSpinner.style.display = "none";
        if (apTriggerText) apTriggerText.textContent = "⚡ Run Auto-Pilot Now";
      }
    });
  }

  function startAutopilotStatusPolling() {
    if (apStatusPollInterval) clearInterval(apStatusPollInterval);
    if (apLiveBanner) apLiveBanner.style.display = "block";
    if (btnTriggerAutopilot) btnTriggerAutopilot.disabled = true;

    apStatusPollInterval = setInterval(async () => {
      try {
        const res = await fetch("/api/autopilot/status");
        const data = await res.json();
        if (!data.success) return;

        const stat = data.status || {};
        const job = stat.current_job;

        if (job && stat.is_executing) {
          if (apLivePct) apLivePct.textContent = `${job.progress || 0}%`;
          if (apLiveProgressFill) apLiveProgressFill.style.width = `${job.progress || 0}%`;
          if (apLiveMsg) apLiveMsg.textContent = job.message || "Executing pipeline...";
        } else {
          // Finished execution
          clearInterval(apStatusPollInterval);
          apStatusPollInterval = null;
          if (btnTriggerAutopilot) {
            btnTriggerAutopilot.disabled = false;
            if (apTriggerSpinner) apTriggerSpinner.style.display = "none";
            if (apTriggerText) apTriggerText.textContent = "⚡ Run Auto-Pilot Now";
          }
          if (apLiveProgressFill) apLiveProgressFill.style.width = "100%";
          if (apLivePct) apLivePct.textContent = "100%";
          if (apLiveMsg) apLiveMsg.textContent = "🎉 Auto-Pilot Execution Completed!";

          setTimeout(() => {
            if (apLiveBanner) apLiveBanner.style.display = "none";
          }, 4000);

          loadAutopilotHistory();
          refreshDashboardGallery();
        }
      } catch (e) {
        console.warn("Auto-Pilot polling error:", e);
      }
    }, 2000);
  }

  // 8. History & Execution Logs
  async function loadAutopilotHistory() {
    if (!apHistoryTableWrapper) return;
    try {
      const res = await fetch("/api/autopilot/history");
      const data = await res.json();
      if (!data.success) return;

      const runs = (data.history && data.history.runs) || [];
      renderAutopilotHistoryTable(runs);
    } catch (err) {
      console.warn("Failed to load Auto-Pilot history:", err);
    }
  }

  function renderAutopilotHistoryTable(runs) {
    if (!apHistoryTableWrapper) return;

    if (!runs || runs.length === 0) {
      apHistoryTableWrapper.innerHTML = `
        <div class="empty-ap-history">
          <div class="empty-icon">⚡</div>
          <h4>No Auto-Pilot Runs Yet</h4>
          <p>Click <strong>⚡ Run Auto-Pilot Now</strong> above or enable the daily schedule switch to start autonomous clipping.</p>
        </div>
      `;
      return;
    }

    let rowsHtml = "";
    runs.forEach((r) => {
      const statusClass = r.status === "completed" ? "completed" : r.status === "running" ? "running" : "failed";
      const statusIcon = r.status === "completed" ? "✅" : r.status === "running" ? "⏳" : "❌";
      const vids = r.videos_processed || [];
      const totalClips = vids.reduce((sum, v) => sum + (v.clips_count || 0), 0);

      let videoPillsHtml = "";
      vids.forEach((v) => {
        videoPillsHtml += `
          <div class="ap-video-preview-mini" title="${v.title}">
            <img src="${v.thumbnail}" class="ap-video-thumb-mini" onerror="this.src='/static/img/fallback.jpg'">
            <div>
              <div class="ap-video-title-mini">${v.country_flag || "🌐"} ${v.title}</div>
              <small style="color:var(--text-muted); font-size:0.75rem;">🎬 ${v.clips_count || 0} Clips • ${v.channel}</small>
            </div>
          </div>
        `;
      });

      rowsHtml += `
        <tr>
          <td>
            <strong>${r.started_at || "Recent"}</strong>
            <div style="font-size:0.75rem; color:var(--text-muted); text-transform:capitalize;">${r.trigger_type || "manual"} trigger</div>
          </td>
          <td>
            <span class="ap-run-status-badge ${statusClass}">
              ${statusIcon} ${r.status.toUpperCase()}
            </span>
          </td>
          <td>
            <span class="badge badge-primary">${vids.length} Videos</span>
          </td>
          <td>
            <span class="badge badge-blue">🎬 ${totalClips} Clips</span>
          </td>
          <td>
            <div style="display:flex; flex-direction:column; gap:6px;">
              ${videoPillsHtml || '<span style="color:var(--text-muted); font-size:0.8rem;">No videos</span>'}
            </div>
          </td>
        </tr>
      `;
    });

    apHistoryTableWrapper.innerHTML = `
      <table class="ap-history-table">
        <thead>
          <tr>
            <th>Date & Trigger</th>
            <th>Status</th>
            <th>Scraped</th>
            <th>Generated</th>
            <th>Processed Videos & Channels</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    `;
  }

  if (btnClearApHistory) {
    btnClearApHistory.addEventListener("click", async () => {
      if (confirm("Clear all Auto-Pilot run history logs?")) {
        try {
          await fetch("/api/autopilot/clear-history", { method: "POST" });
          loadAutopilotHistory();
        } catch (e) {
          console.error(e);
        }
      }
    });
  }

  // ==========================================================
  // 10. INITIAL DATA LOADS (Triggered cleanly on startup)
  // ==========================================================
  refreshDashboardGallery();
  refreshSocialAccounts();
  refreshPostHistory();
  loadAutopilotConfigAndStatus();
});

// ==========================================================
// 10. GLOBAL AUTH TUTORIAL INTERACTION HELPERS
// ==========================================================
window.toggleTutorial = function (plat) {
  const card = document.getElementById(`card-tutorial-${plat}`);
  if (card) {
    card.classList.toggle("open");
  }
};

window.copyToClipboard = async function (btn, text) {
  try {
    await navigator.clipboard.writeText(text);
    const origText = btn.textContent;
    btn.textContent = "✓ Copied!";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.textContent = origText;
      btn.classList.remove("copied");
    }, 2000);
  } catch (err) {
    prompt("Copy this snippet manually:", text);
  }
};
