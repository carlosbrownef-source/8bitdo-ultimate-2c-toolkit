// SPDX-License-Identifier: GPL-3.0-or-later
// Only for tests: loaded when the address has ?diagsim=<state>. Simulates what the page can't get in a browser.
(() => {
  const query = new URLSearchParams(location.search);
  const realFetch = window.fetch;
  window.fetch = async (url, options) => {
    const answer = await realFetch(url, options);
    if (String(url).startsWith("/api/firmware") && query.get("identity") === "none") {
      const data = await answer.json();
      data.boot_identity = null;
      return new Response(JSON.stringify(data), { status: answer.status });
    }
    return answer;
  };
})();
