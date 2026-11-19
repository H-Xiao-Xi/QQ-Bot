function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderBoard(id, rows, emptyText, html) {
  const body = document.getElementById(id);
  if (!body) return;
  if (!rows.length) {
    const cols = { "point-board": 7, "rob-board": 5, "bank-board": 6 };
    body.innerHTML = `<tr class="empty"><td colspan="${cols[id] || 5}">${emptyText}</td></tr>`;
    return;
  }
  body.innerHTML = rows.map(html).join("");
}

function isEditing(id) {
  const root = document.getElementById(id);
  return Boolean(root && root.contains(document.activeElement));
}

async function refresh() {
  const res = await fetch("/api/status");
  if (res.status === 401) {
    window.location.href = "/login";
    return;
  }
  if (res.status === 403) {
    window.location.href = "/account";
    return;
  }
  if (!res.ok) return;
  const data = await res.json();
  const set = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };
  set("stat-received", data.stats.received);
  set("stat-validated", data.stats.validated);
  set("stat-replied", data.stats.replied);
  set("stat-errors", data.stats.errors);
  set("uptime", data.uptime_seconds);
  set("secret-len", data.secret_len || 0);
  set("secret-suffix", data.secret_suffix || "未配置");

  const checkin = data.checkin || {};
  set("ck-day", checkin.day || "");
  set("ck-today", checkin.today_count || 0);
  set("ck-users", checkin.user_count || 0);
  set("ck-times", checkin.checkin_count || 0);
  set("ck-points", checkin.points_sum || 0);
  set("ck-bank", checkin.bank_sum || 0);
  renderBoard("today-board", checkin.today || [], "今天还没有人签到", (row) => `
    <tr>
      <td>${esc(row.rank)}</td>
      <td>${esc(row.nickname)}</td>
      <td>+${esc(row.gained)}</td>
      <td>${esc(row.streak)}</td>
      <td>${esc(row.points)}</td>
    </tr>
  `);
  if (!isEditing("point-board")) {
    renderBoard("point-board", checkin.leaderboard || [], "还没有签到记录", (row, index) => `
    <tr>
      <td>${index + 1}</td>
      <td>${esc(row.nickname)}</td>
      <td><input class="mini" type="number" min="0" step="1" value="${esc(row.streak)}" data-field="streak"></td>
      <td>${esc(row.total)}</td>
      <td><input class="mini" type="number" min="0" step="1" value="${esc(row.points)}" data-field="points"></td>
      <td><input class="mini" type="number" min="0" step="1" value="${esc(row.bank || 0)}" data-field="bank"></td>
      <td><button type="button" class="mini-save" data-user="${esc(row.user_id)}">保存</button></td>
    </tr>
  `);
  }

  set("rob-today", checkin.rob_today || 0);
  set("rob-win", checkin.rob_wins || 0);
  renderBoard("rob-board", checkin.robs || [], "还没有打劫记录", (row) => {
    const ok = Boolean(row.success);
    const delta = ok ? `+${esc(row.stolen)}` : (row.lost ? `-${esc(row.lost)}` : "0");
    return `
    <tr>
      <td>${esc(row.time)}</td>
      <td>${esc(row.attacker)}</td>
      <td>${esc(row.victim)}</td>
      <td class="${ok ? "win" : "lose"}">${ok ? "得手" : "失手"}</td>
      <td class="${ok ? "win" : "lose"}">${delta}</td>
    </tr>
  `;
  });

  set("bank-today", checkin.bank_today || 0);
  renderBoard("bank-board", checkin.banks || [], "还没有银行流水", (row) => {
    const action = row.action === "deposit" ? "存款" : row.action === "withdraw" ? "取款" : row.action === "interest" ? "利息" : "调整";
    let delta = String(row.amount || 0);
    if (row.action === "deposit") delta = `+${esc(row.amount)}`;
    else if (row.action === "withdraw") delta = `-${esc(row.amount)}`;
    else delta = Number(row.amount) >= 0 ? `+${esc(row.amount)}` : `${esc(row.amount)}`;
    return `
    <tr>
      <td>${esc(row.time)}</td>
      <td>${esc(row.user)}</td>
      <td>${action}</td>
      <td>${delta}</td>
      <td>${esc(row.points)}</td>
      <td>${esc(row.bank)}</td>
    </tr>
  `;
  });

  const pill = document.querySelector(".pill");
  if (pill) {
    pill.classList.toggle("on", data.configured);
    pill.textContent = data.configured ? "凭证已加载" : "等待配置 AppID / AppSecret";
  }

  const log = document.getElementById("event-log");
  if (!log) return;
  if (!data.events.length) return;
  log.innerHTML = data.events.map((item) => `
    <div class="row ${item.ok ? "" : "bad"}">
      <time>${item.time}</time>
      <b>${item.kind}</b>
      <span>${item.summary}</span>
    </div>
  `).join("");
}

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.textContent = "已复制";
    } catch (err) {
      button.textContent = "复制失败";
    }
  });
});

setInterval(refresh, 2500);

const form = document.getElementById("cred-form");
if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const msg = document.getElementById("cred-msg");
    const appId = document.getElementById("app-id").value.trim();
    const appSecret = document.getElementById("app-secret").value.trim();
    msg.className = "hint";
    msg.textContent = "正在保存…";
    const res = await fetch("/api/credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ app_id: appId, app_secret: appSecret }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      msg.className = "hint bad";
      msg.textContent = data.detail || "保存失败";
      return;
    }
    document.getElementById("app-secret").value = "";
    document.getElementById("app-secret").placeholder = "已保存，留空则保持不变";
    msg.className = "hint ok";
    msg.textContent = `已保存，Secret 长度 ${data.secret_len || 0}，末四位 ${data.secret_suffix || ""}。Webhook 立即使用新密钥。`;
    refresh();
  });
}

const checkBtn = document.getElementById("cred-check");
if (checkBtn) {
  checkBtn.addEventListener("click", async () => {
    const msg = document.getElementById("cred-msg");
    msg.className = "hint";
    msg.textContent = "正在向开放平台检测密钥…";
    const res = await fetch("/api/credentials/check", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      msg.className = "hint bad";
      msg.textContent = data.detail || "检测失败";
      return;
    }
    if (data.token_ok) {
      msg.className = "hint ok";
      msg.textContent = `密钥可用。AppID ${data.app_id}，Secret 长度 ${data.secret_len}，末四位 ${data.secret_suffix}。`;
      return;
    }
    msg.className = "hint bad";
    msg.textContent = `密钥检测失败：${data.token_error || "未知错误"}。若提示 IP 白名单，先把服务器公网 IP 加进管理端。`;
  });
}

const pointBoard = document.getElementById("point-board");
if (pointBoard) {
  pointBoard.addEventListener("click", async (event) => {
    const button = event.target.closest(".mini-save");
    if (!button) return;
    const row = button.closest("tr");
    const userId = button.dataset.user || "";
    const points = Number(row.querySelector('[data-field="points"]')?.value);
    const streak = Number(row.querySelector('[data-field="streak"]')?.value);
    const bank = Number(row.querySelector('[data-field="bank"]')?.value);
    const msg = document.getElementById("ck-edit-msg");
    if (!Number.isInteger(points) || !Number.isInteger(streak) || !Number.isInteger(bank) || points < 0 || streak < 0 || bank < 0) {
      if (msg) {
        msg.className = "hint bad";
        msg.textContent = "钱包、银行和天数必须是大于等于 0 的整数";
      }
      return;
    }
    button.disabled = true;
    const res = await fetch("/api/checkin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, points, streak, bank }),
    });
    const data = await res.json().catch(() => ({}));
    button.disabled = false;
    if (!res.ok) {
      if (msg) {
        msg.className = "hint bad";
        msg.textContent = data.detail || "保存失败";
      }
      return;
    }
    if (msg) {
      msg.className = "hint ok";
      msg.textContent = `已保存 ${data.nickname || userId}：钱包 ${data.points}，银行 ${data.bank}，连续 ${data.streak} 天`;
    }
    button.blur();
    refresh();
  });
}
