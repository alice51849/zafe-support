(function () {
  "use strict";

  const locales = window.ZAFE_LOCALES || {};
  const supported = Object.keys(locales);
  const query = new URLSearchParams(window.location.search);
  const requested = query.get("lang");
  const browserLocale = navigator.language || "en-US";
  const languageOnly = browserLocale.split("-")[0].toLowerCase();
  const detected = supported.find((locale) => locale.toLowerCase() === browserLocale.toLowerCase())
    || supported.find((locale) => locale.split("-")[0].toLowerCase() === languageOnly)
    || "en-US";
  const locale = supported.includes(requested) ? requested : detected;
  const copy = locales[locale] || locales["en-US"];

  document.documentElement.lang = locale;
  document.documentElement.dir = copy.direction;

  document.querySelectorAll("[data-zafe]").forEach((element) => {
    const key = element.dataset.zafe;
    if (Object.prototype.hasOwnProperty.call(copy, key)) {
      element.textContent = copy[key];
    }
  });

  const page = document.body.dataset.page;
  if (page === "privacy") {
    document.title = copy.privacyTitle;
  } else if (page === "support") {
    document.title = copy.supportTitle;
  } else {
    document.title = `${copy.name} — ${copy.homeTitle}`;
  }
  const meta = document.querySelector('meta[name="description"]');
  if (meta) meta.content = copy.promo;

  const paths = {
    home: "index.html",
    support: "support.html",
    privacy: "privacy.html"
  };
  document.querySelectorAll("[data-page-link]").forEach((link) => {
    const target = paths[link.dataset.pageLink];
    if (target) link.href = `${target}?lang=${encodeURIComponent(locale)}`;
  });

  const picker = document.getElementById("localePicker");
  if (picker) {
    supported.forEach((code) => {
      const option = document.createElement("option");
      option.value = code;
      option.textContent = `${locales[code].languageName} — ${code}`;
      option.selected = code === locale;
      picker.appendChild(option);
    });
    picker.addEventListener("change", () => {
      const next = encodeURIComponent(picker.value);
      window.location.assign(`${window.location.pathname}?lang=${next}`);
    });
  }
})();
