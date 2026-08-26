/* ═══════════════════════════════════════════════════════════
   宝山实验 · AI 辅助调用工具（百度千帆 ERNIE）
   每个岛屿页面引入：<script src="assets/ai-helper.js"></script>
   公开 API：
     - AIHelper.getKey() / AIHelper.setKey()
     - AIHelper.call(systemPrompt, userPrompt) → Promise<string>
     - AIHelper.parseJson(text) → object | null
     - AIHelper.escapeHtml(s) → string
     - AIHelper.injectKeyButton(parent, opts) → 在指定容器注入 🔑 按钮
   ═══════════════════════════════════════════════════════════ */
(function(global){
  // 🔒 安全说明：前端不再持有任何 API Key
  //   - 所有 AI 调用都走后端代理 /api/ai/chat
  //   - 密钥仅在服务端 server/.env 中（BAIDU_AI_KEY）
  //   - 浏览器 DevTools / 源码 / Network 都看不到 Key
  const PROXY_URL = '/api/ai/chat';

  // 清掉历史残留（旧版本可能在 localStorage 里存过 key/model）
  try {
    localStorage.removeItem('bs_ai_key');
    localStorage.removeItem('bs_ai_model');
    sessionStorage.removeItem('bs_ai_mode');
  } catch(e){}

  // 这些方法保留下来仅为兼容，**永远返回空** —— 前端不再持有 Key
  function getKey(){ return ''; }
  function setKey(){
    if(typeof window !== 'undefined' && window.console)
      console.warn('[AI] 前端不再支持本地 Key；密钥由后端管理');
    return false;
  }

  const SAFETY = `【重要安全要求 · 必须严格遵守】
1. 受众是 8-12 岁小学生，所有输出必须健康、积极、安全
2. 严格禁止：性、暴力、政治、宗教、毒品、自残、歧视、恐怖、过激情绪
3. 不要给孩子贴负面标签（如"差""笨""有问题"）；体测薄弱项要说"还可以加强""下次会更厉害"
4. 不要替代家长、老师或医生的专业判断
5. 数据不足或异常时，请温和说明，不要编造
6. 不要自称是某个角色（如"小宝""小图"），用"我"或不自称即可

【语气要求】
活泼、有童心、鼓励、像哥哥姐姐对小朋友说话，可适量使用 emoji，不要 markdown 不要代码块

【JSON 输出严格要求】
- 整个回复只能是一个有效的 JSON 对象，不要任何前后缀文字
- 字符串值内禁止出现真实换行/制表符，需要换行用 \\n 转义
- 不要在 JSON 末尾加 markdown 代码块标记`;

  async function call(systemPrompt, userPrompt){
    // 强制走后端代理（前端不再持有 Key，无降级、无直连）
    const headers = {'Content-Type':'application/json'};
    const sess = sessionStorage.getItem('bs_session_token');
    if(sess) headers['Authorization'] = `Bearer ${sess}`;
    const res = await fetch(PROXY_URL, {
      method:'POST', headers,
      body: JSON.stringify({system: systemPrompt, user: userPrompt})
    });
    const data = await res.json().catch(()=>({}));
    if(!res.ok){
      throw new Error(data.error || `AI 服务异常 (${res.status})`);
    }
    return data.content || '';
  }

  function parseJson(text){
    if(!text) return null;
    // 1. 剥 markdown 代码块
    let t = text.replace(/```json\s*/gi,'').replace(/```\s*/g,'').trim();
    // 2. 找到从第一个 { 到最后一个 } 的内容
    const a = t.indexOf('{'), b = t.lastIndexOf('}');
    if(a < 0 || b < 0 || b <= a) return null;
    let raw = t.slice(a, b+1);
    // 3. 直接解析
    try { return JSON.parse(raw); } catch(e){}
    // 4. 容错：把字符串值里的真实换行/制表符转义；去掉对象/数组末尾的多余逗号
    let fixed = raw
      .replace(/,(\s*[}\]])/g, '$1')                   // 去掉 ,} 或 ,]
      .replace(/[""]/g, '"')                            // 全角引号 → 半角
      .replace(/(?<=:\s*"[^"]*)\n/g, '\\n')             // 字符串里的真实 \n
      .replace(/(?<=:\s*"[^"]*)\t/g, '\\t');            // 字符串里的真实 \t
    try { return JSON.parse(fixed); } catch(e){}
    // 5. 兜底：把所有字符串内部的换行符替换（非 lookbehind 兜底）
    fixed = raw.replace(/"((?:\\.|[^"\\])*)"/g, (_, body) =>
      '"' + body.replace(/\n/g,'\\n').replace(/\r/g,'').replace(/\t/g,'\\t') + '"'
    ).replace(/,(\s*[}\]])/g, '$1');
    try { return JSON.parse(fixed); } catch(e){ return null; }
  }

  function escapeHtml(s){
    return String(s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  function _toast(msg){
    let t = document.getElementById('toast');
    if(t && typeof window.showToast === 'function'){
      window.showToast(msg);
    } else {
      const el = document.createElement('div');
      el.textContent = msg;
      el.style.cssText = `
        position:fixed;left:50%;top:80px;transform:translateX(-50%);
        background:#0E5E80;color:#fff;padding:12px 22px;border-radius:24px;
        font-weight:800;font-size:14px;letter-spacing:1px;
        box-shadow:0 10px 26px rgba(14,94,128,.35);z-index:99999;
      `;
      document.body.appendChild(el);
      setTimeout(()=>el.remove(), 2400);
    }
  }

  global.AIHelper = { getKey, setKey, call, parseJson, escapeHtml, SAFETY };
})(window);
