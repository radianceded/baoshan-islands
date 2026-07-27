/* ═══════════════════════════════════════════════════════════
   数字美术馆 · 评论 & 点赞系统
   - 点赞：localStorage art_likes_{workId} → [name, ...]
   - 评论：localStorage art_comments_{workId} → [{id,name,text,time}, ...]
   - 坏词过滤：中文关键词 + 正则混淆检测 + AI 可替换为远程审核
   ═══════════════════════════════════════════════════════════ */
(function(global){
  'use strict';

  /* ───────── 坏词过滤器 ───────── */
  const BAD_WORDS_CN = [
    // 辱骂
    '傻逼','脑残','白痴','废物','垃圾','去死','滚蛋','滚开','滚出去',
    '混蛋','蠢货','弱智','低能','智障','贱','畜','婊','操','靠',
    '他妈','你妈','他妈','艹','卧槽','我操','坑爹','日了',
    // 攻击
    '恶心','丑陋','丢人','丢脸','不要脸',
    // 暴力 / 歧视
    '打死','杀掉','去死','砍死','弄死',
    // 广告 / spam
    '加微信','加我微信','微商','代理','赚钱','日赚','兼职',
    '免费领取','点击领取','红包','返利','刷单','彩票','网赚',
    // 常见变异
    's b','sb','nmsl','n m s l','cnm','tmd','fuck','shit','damn',
    'ass','bitch','dick','bastard','crap','hell',
    // 空白绕行检测由正则处理
  ];

  const BAD_PATTERNS = [
    // 拆字 / 同音替换
    /[傻煞沙][逼比笔必鼻]/i,
    /[脑恼][残参蚕]/i,
    /[白百败][痴吃嗤]/i,
    /[卧我握][槽草曹]/i,
    /[你尼泥][妈吗马码]/i,
    /[操草曹][你尼泥]/i,
    /[滚衮][蛋但旦]/i,
    /[贱见建][人仁任]/i,
    // 英文变体
    /\bf[uù]+[cç]k\b/i,
    /\bsh[i1!]t\b/i,
    /\b[àa]ss\b/i,
    /\bd[a@]mn\b/i,
    /\bb[i1!]tch\b/i,
    /\bd[i1!]ck\b/i,
    // 广告特征
    /[＋+加]\s*[vV微]\s*[信xX]/,
    /[vV微]\s*[信xX]\s*[:：]?\s*[a-zA-Z0-9_-]{5,}/,
    /\b\d{6,}\b/,                         // 连续6位以上数字（QQ/手机号嫌疑）
    /(日[赚挣入]|[赚挣]\d+[元块])/,
    // 重复字母 spam
    /(.)\1{7,}/,                          // 同一字符连续8次以上
  ];

  /** 检查文本是否包含坏词 */
  function isBadContent(text){
    if(!text) return false;
    const t = text.toLowerCase().replace(/\s+/g, '');

    // 1. 关键词精确匹配（去除空格后）
    for(const w of BAD_WORDS_CN){
      if(t.includes(w.toLowerCase())) return true;
    }

    // 2. 正则模式匹配
    for(const p of BAD_PATTERNS){
      if(p.test(text) || p.test(t)) return true;
    }

    return false;
  }

  /* ═══════════ 中文语义情感分析 ═══════════ */

  // 负面情感词（分值 -1 ~ -3，越负面绝对值越大）
  const NEG_WORDS = {
    // 强烈贬低 (-3)
    '垃圾':-3, '恶心':-3, '丑死':-3, '烂透':-3, '差劲':-3, '一塌糊涂':-3, '不堪入目':-3,
    '什么玩意':-3, '什么鬼':-3, '这也叫':-3, '就这':-3, '呵呵':-2,
    // 明显负面 (-2)
    '难看':-2, '很丑':-2, '太丑':-2, '真丑':-2, '好丑':-2,
    '很差':-2, '太差':-2, '真差':-2, '糟糕':-2, '差评':-2,
    '讨厌':-2, '厌恶':-2, '不喜欢':-2, '烦':-2, '无聊':-2, '没意思':-2,
    '浪费时间':-2, '不怎么样':-2, '不行':-2, '失败':-2,
    // 轻度负面 (-1)
    '不好看':-1, '不太好':-1, '不好':-1, '一般般':-1, '还行吧':-1,
    '失望':-1, '可惜':-1, '遗憾':-1, '勉强':-1, '凑合':-1,
    '有点乱':-1, '不太清楚':-1, '糊':-1, '暗':-1,
  };

  // 正面情感词（分值 +1 ~ +2，仅用于抵消轻微负面，不单独加分）
  const POS_WORDS = new Set([
    '好看','漂亮','美','棒','赞','好','优秀','厉害','精彩','出色',
    '喜欢','爱','欣赏','感动','惊艳','震撼','绝了','太棒','真棒',
    '很棒','非常好','特别好','不错','还行','可以','有意思','有趣',
    '生动','细腻','精致','用心','有创意','有想法','有天赋','天才',
    '加油','继续努力','期待','支持',
  ]);

  // 否定词（翻转紧跟的情感词极性）
  const NEGATION = new Set(['不','没','无','非','别','莫','未','勿','休']);

  // 程度副词（放大紧跟的情感词分值 ×1.5）
  const INTENSIFIERS = new Set(['很','非常','特别','太','真','好','超','极','挺','蛮','尤其','格外']);

  /**
   * 简单中文分词：基于词典的最长匹配
   * 返回 [{word, start}] 数组
   */
  function tokenizeChinese(text){
    const tokens = [];
    const len = text.length;
    let i = 0;
    while(i < len){
      let matched = null;
      // 尝试最长 4 字词 → 2 字词
      for(let wlen = Math.min(4, len - i); wlen >= 1; wlen--){
        const cand = text.substring(i, i + wlen);
        if(cand in NEG_WORDS || POS_WORDS.has(cand) || NEGATION.has(cand) || INTENSIFIERS.has(cand)){
          matched = cand;
          break;
        }
      }
      if(matched){
        tokens.push({word: matched, start: i});
        i += matched.length;
      } else {
        i++;
      }
    }
    return tokens;
  }

  /**
   * 情感打分
   * 返回 {score, negative, reason} — score 越负越差
   */
  function analyzeSentiment(text){
    if(!text || text.trim().length < 2) return {score:0, negative:false, reason:''};

    const t = text.trim();
    const tokens = tokenizeChinese(t);
    if(!tokens.length) return {score:0, negative:false, reason:''};

    let score = 0;
    let negReasons = [];

    for(let idx = 0; idx < tokens.length; idx++){
      const tok = tokens[idx];

      // 跳过否定词和程度词，它们修饰后续词
      if(NEGATION.has(tok.word) || INTENSIFIERS.has(tok.word)) continue;

      // 检查前方 1-2 个 token 内是否有否定词
      let negated = false;
      let intensified = false;
      for(let lookback = 1; lookback <= 2; lookback++){
        const prev = tokens[idx - lookback];
        if(!prev) break;
        if(INTENSIFIERS.has(prev.word)) intensified = true;
        // 程度词不阻断否定词检测，继续往前看
        if(prev.word === '不' || prev.word === '没' || prev.word === '别' || prev.word === '无'){
          negated = true;
        }
      }

      // 负面词
      if(tok.word in NEG_WORDS){
        let v = NEG_WORDS[tok.word];
        if(negated) v = Math.abs(v);  // 否定+负面 → 变正面（"不难看"→+2）
        if(intensified) v = Math.round(v * 1.5);
        score += v;
        if(v <= -1) negReasons.push(tok.word);
        continue;
      }

      // 正面词（仅当被否定时才扣分，否则不参与打分避免假阳性）
      if(POS_WORDS.has(tok.word)){
        if(negated){
          score -= 1;  // "不好看" → -1
          negReasons.push(tok.word + '(否定)');
        }
        // 正面词不被否定时忽略（避免"很好看"→拉高阈值绕过检测）
      }
    }

    // 额外检测：反问/讽刺模式
    if(/[?？]/.test(t) && score < 0){
      score -= 1;  // 带问号的负面更可能是嘲讽
    }
    if(/(这也|就这|呵呵|笑了|无语)/.test(t) && score <= -1){
      score -= 1;
    }

    // 如果全是英文/符号无中文，不判断情感
    if(!/[\u4e00-\u9fff]/.test(t)){
      return {score:0, negative:false, reason:''};
    }

    const negative = score <= -1;  // ≤-1 视为负面评论
    const reason = negative ? ('检测到负面情绪：' + negReasons.join('、')) : '';

    return {score, negative, reason};
  }

  /** 清洗文本：坏词过滤 + 语义情感分析 */
  function moderateText(text){
    if(!text || !text.trim()) return { ok: false, reason: '内容为空' };
    if(text.trim().length > 500) return { ok: false, reason: '评论过长（最多500字）' };

    // 1. 坏词检测
    if(isBadContent(text)){
      return { ok: false, reason: '评论包含不当内容，请修改后重试 🙏' };
    }

    // 2. 语义情感分析：负面情绪拦截
    const sentiment = analyzeSentiment(text);
    if(sentiment.negative){
      return { ok: false, reason: '请保持友善哦～ ' + sentiment.reason };
    }

    return { ok: true, text: text.trim() };
  }

  /* ───────── localStorage 键名 ───────── */
  function likeKey(workId){ return 'art_likes_' + workId; }
  function commentKey(workId){ return 'art_comments_' + workId; }

  /** 获取点赞列表 */
  function getLikes(workId){
    try {
      return JSON.parse(localStorage.getItem(likeKey(workId)) || '[]');
    } catch(e){ return []; }
  }

  /** 保存点赞列表 */
  function saveLikes(workId, arr){
    try { localStorage.setItem(likeKey(workId), JSON.stringify(arr)); } catch(e){}
  }

  /** 获取评论列表 */
  function getComments(workId){
    try {
      return JSON.parse(localStorage.getItem(commentKey(workId)) || '[]');
    } catch(e){ return []; }
  }

  /** 保存评论列表 */
  function saveComments(workId, arr){
    try { localStorage.setItem(commentKey(workId), JSON.stringify(arr)); } catch(e){}
  }

  /** 获取当前登录用户名 */
  function currentUser(){
    return sessionStorage.getItem('artUser') || '访客';
  }

  /* ───────── 公开 API ───────── */
  const ArtComments = {

    /** 当前用户是否已点赞 */
    hasLiked(workId, userName){
      return getLikes(workId).includes(userName || currentUser());
    },

    /** 获取点赞数 */
    likeCount(workId){
      return getLikes(workId).length;
    },

    /** 切换点赞 */
    toggleLike(workId, onUpdate){
      const likes = getLikes(workId);
      const name = currentUser();
      const idx = likes.indexOf(name);
      if(idx >= 0){
        likes.splice(idx, 1);
      } else {
        likes.push(name);
      }
      saveLikes(workId, likes);
      // 同步到服务端（静默失败，不影响本地体验）
      fetch('/api/art-like', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({work_id:workId, user_name:name, action: idx>=0?'remove':'add'})
      }).catch(function(){});
      if(onUpdate) onUpdate(likes.length, idx < 0);
      return { count: likes.length, liked: idx < 0 };
    },

    /** 获取评论列表 */
    getComments(workId){
      return getComments(workId);
    },

    /** 添加评论 */
    addComment(workId, text){
      const result = moderateText(text);
      if(!result.ok) return result;

      const comments = getComments(workId);
      const entry = {
        id: 'c' + Date.now() + '_' + Math.random().toString(36).slice(2,6),
        name: currentUser(),
        text: result.text,
        time: Date.now()
      };
      comments.push(entry);
      saveComments(workId, comments);
      // 同步到服务端（静默失败，不影响本地体验）
      fetch('/api/art-comment', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({work_id:workId, user_name:entry.name, text:entry.text})
      }).catch(function(){});
      return { ok: true, entry, comments };
    },

    /** 删除评论 */
    removeComment(workId, commentId){
      const comments = getComments(workId);
      const idx = comments.findIndex(c => c.id === commentId);
      if(idx >= 0 && comments[idx].name === currentUser()){
        comments.splice(idx, 1);
        saveComments(workId, comments);
        return true;
      }
      return false;
    },

    /** 获取某作品总互动数（点赞+评论） */
    engagementCount(workId){
      return getLikes(workId).length + getComments(workId).length;
    },

    /** 渲染点赞按钮 HTML */
    likeBtnHTML(workId){
      const count = this.likeCount(workId);
      const liked = this.hasLiked(workId);
      return `<button class="like-btn${liked?' liked':''}" data-work="${workId}" onclick="ArtComments.toggleLikeUI(this)" title="${liked?'取消点赞':'点赞'}">
        <span class="like-icon">${liked?'❤️':'🤍'}</span>
        <span class="like-count">${count || ''}</span>
      </button>`;
    },

    /** 渲染评论按钮 HTML */
    commentBtnHTML(workId){
      const count = getComments(workId).length;
      return `<button class="comment-btn" data-work="${workId}" onclick="ArtComments.openComments('${workId}')" title="查看评论">
        <span>💬</span>
        <span class="comment-count">${count || ''}</span>
      </button>`;
    },

    /** 点赞点击处理 */
    toggleLikeUI(btn){
      const workId = btn.dataset.work;
      const result = this.toggleLike(workId);
      const icon = btn.querySelector('.like-icon');
      const cnt = btn.querySelector('.like-count');
      if(result.liked){
        btn.classList.add('liked');
        icon.textContent = '❤️';
      } else {
        btn.classList.remove('liked');
        icon.textContent = '🤍';
      }
      cnt.textContent = result.count || '';
    },

    /** 打开评论面板 */
    openComments(workId){
      const name = currentUser();
      const comments = this.getComments(workId);

      // 移除已有面板
      document.querySelectorAll('.comment-panel').forEach(p => p.remove());

      const panel = document.createElement('div');
      panel.className = 'comment-panel';
      panel.innerHTML = `
        <div class="cp-header">
          <span class="cp-title">💬 留言板</span>
          <span class="cp-count">${comments.length} 条留言</span>
          <button class="cp-close" onclick="this.closest('.comment-panel').remove()">✕</button>
        </div>
        <div class="cp-list">
          ${comments.length === 0
            ? '<div class="cp-empty">✨ 还没有留言，来说点什么吧</div>'
            : comments.map(c => `
              <div class="cp-item">
                <div class="cp-avatar">${(c.name||'?')[0]}</div>
                <div class="cp-body">
                  <div class="cp-name">${escapeHtml(c.name)}
                    ${c.name === name ? '<span class="cp-self">你</span>' : ''}
                    <span class="cp-time">${timeAgo(c.time)}</span>
                    ${c.name === name ? `<button class="cp-del" onclick="ArtComments.delComment('${c.id}','${workId}')">删除</button>` : ''}
                  </div>
                  <div class="cp-text">${escapeHtml(c.text)}</div>
                </div>
              </div>
            `).join('')
          }
        </div>
        <div class="cp-input-row">
          <input class="cp-input" id="cpInput_${workId}" placeholder="写下你的留言..." maxlength="500" onkeydown="if(event.key==='Enter')ArtComments.submitComment('${workId}')">
          <button class="cp-send" onclick="ArtComments.submitComment('${workId}')">发送</button>
        </div>
      `;
      document.body.appendChild(panel);

      // 聚焦输入框
      setTimeout(() => {
        const inp = document.getElementById('cpInput_' + workId);
        if(inp) inp.focus();
      }, 100);
    },

    /** 提交评论 */
    submitComment(workId){
      const inp = document.getElementById('cpInput_' + workId);
      if(!inp) return;
      const text = inp.value.trim();
      if(!text) return;

      const result = this.addComment(workId, text);
      if(!result.ok){
        // 显示错误
        const row = inp.parentElement;
        let errEl = row.querySelector('.cp-err');
        if(!errEl){
          errEl = document.createElement('div');
          errEl.className = 'cp-err';
          row.appendChild(errEl);
        }
        errEl.textContent = result.reason;
        errEl.style.display = 'block';
        setTimeout(() => { errEl.style.display = 'none'; }, 3000);
        return;
      }

      inp.value = '';
      // 刷新面板
      this.openComments(workId);
      // 更新评论按钮计数
      this.refreshBtnCounts(workId);
    },

    /** 删除评论 */
    delComment(commentId, workId){
      if(!confirm('确定删除这条留言吗？')) return;
      this.removeComment(workId, commentId);
      this.openComments(workId);
      this.refreshBtnCounts(workId);
    },

    /** 刷新作品卡片上的按钮计数 */
    refreshBtnCounts(workId){
      const btns = document.querySelectorAll(`.comment-btn[data-work="${workId}"] .comment-count`);
      const cnt = getComments(workId).length;
      btns.forEach(b => { b.textContent = cnt || ''; });
    },

    /** 检查登录状态，未登录跳转 */
    requireLogin(){
      const name = sessionStorage.getItem('artUser');
      if(!name){
        location.replace('art-login.html');
        return null;
      }
      return name;
    }
  };

  /* ───────── 工具函数 ───────── */
  function escapeHtml(s){
    return String(s||'').replace(/[<>&"']/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function timeAgo(ts){
    const diff = Date.now() - ts;
    if(diff < 60000) return '刚刚';
    if(diff < 3600000) return Math.floor(diff/60000) + '分钟前';
    if(diff < 86400000) return Math.floor(diff/3600000) + '小时前';
    if(diff < 604800000) return Math.floor(diff/86400000) + '天前';
    const d = new Date(ts);
    return d.getFullYear() + '/' + (d.getMonth()+1) + '/' + d.getDate();
  }

  global.ArtComments = ArtComments;
})(window);
