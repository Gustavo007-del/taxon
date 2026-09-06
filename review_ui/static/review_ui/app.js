/* review_ui/app.js — lightweight integration between the rendered pages and
 * the DRF API (/api/). No build step; plain fetch() + DOM updates.
 *
 * Responsibilities:
 *   1. Run text/image classification passes from the dashboard and poll
 *      GET /api/batch/<id>/ until the job finishes.
 *   2. (Optional) helper for approve/override PATCHes elsewhere.
 */
(function () {
  "use strict";

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : null;
  }

  /* fetch wrapper that sends JSON with the CSRF header on non-GET requests. */
  function apiFetch(url, options) {
    options = options || {};
    var headers = options.headers || {};
    if (!(headers instanceof Headers)) {
      headers = new Headers(headers);
    }
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
      headers.set("X-CSRFToken", getCookie("csrftoken") || "");
      options.body = JSON.stringify(options.body);
    }
    options.headers = headers;
    return fetch(url, options).then(function (response) {
      if (!response.ok) {
        return response.json().then(function (err) {
          throw new Error((err && (err.detail || JSON.stringify(err))) || response.status);
        });
      }
      return response.json();
    });
  }

  function jobLabel(type) {
    return type === "image" ? "Image pass" : "Text pass";
  }

  /* Insert + keep a live progress card for one batch job. */
  function trackJob(job) {
    var container = document.getElementById("batch-progress");
    if (!container) return;

    var card = document.createElement("div");
    card.className =
      "bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex items-center gap-4";
    card.innerHTML =
      '<div class="flex-1">' +
      '<div class="flex justify-between text-sm mb-1">' +
      '<span class="font-medium">' + jobLabel(job.job_type) + ' <span class="text-gray-400">#' + job.id + '</span></span>' +
      '<span class="job-status text-gray-500">starting…</span>' +
      "</div>" +
      '<div class="flex items-center gap-3">' +
      '<div class="flex-1 bg-gray-200 rounded h-2 overflow-hidden">' +
      '<div class="job-bar h-2 bg-blue-500 rounded transition-all" style="width:0%"></div>' +
      "</div>" +
      '<span class="job-count text-xs text-gray-500 whitespace-nowrap">0/0</span>' +
      "</div>" +
      "</div>";

    container.prepend(card);
    var bar = card.querySelector(".job-bar");
    var count = card.querySelector(".job-count");
    var statusEl = card.querySelector(".job-status");

    var timer = setInterval(function () {
      apiFetch("/api/batch/" + job.id + "/").then(function (data) {
        var total = data.total || 0;
        var processed = data.processed || 0;
        var pct = total ? Math.min(100, Math.round((100 * processed) / total)) : 0;
        bar.style.width = pct + "%";
        count.textContent = processed + "/" + total;
        if (data.failed) statusEl.textContent = data.failed + " failed";

        if (data.status === "completed") {
          statusEl.textContent = "completed";
          bar.className = "job-bar h-2 bg-green-500 rounded transition-all";
          clearInterval(timer);
          setTimeout(function () { window.location.reload(); }, 800);
        } else if (data.status === "failed") {
          statusEl.textContent = "failed";
          bar.className = "job-bar h-2 bg-red-500 rounded transition-all";
          clearInterval(timer);
          setTimeout(function () { window.location.reload(); }, 1200);
        } else {
          statusEl.textContent = "running…";
        }
      }).catch(function () {
        // keep polling; the runner may briefly be unavailable
      });
    }, 2000);
  }

  function runBatch(jobType) {
    var limitInput = document.getElementById("batch-limit");
    var payload = { job_type: jobType };
    if (limitInput && limitInput.value && parseInt(limitInput.value, 10) > 0) {
      payload.limit = parseInt(limitInput.value, 10);
    }

    apiFetch("/api/batch/run/", {
      method: "POST",
      body: payload,
    }).then(function (job) {
      trackJob(job);
    }).catch(function (err) {
      alert("Could not start batch: " + err.message);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var buttons = document.querySelectorAll("[data-run]");
    Array.prototype.forEach.call(buttons, function (button) {
      button.addEventListener("click", function () {
        var type = button.getAttribute("data-run");
        if (type) runBatch(type);
      });
    });
  });
})();
