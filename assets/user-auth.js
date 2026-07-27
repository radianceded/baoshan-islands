/* ═══════════════════════════════════════════════════════════
   宝山学习群岛 · 前端身份/角色助手
   - 老师端：可看到全部学生 + 自定义学生切换
   - 家长端：只看到自己绑定的孩子，无切换、无添加

   identity 来源优先级：
     1. URL 参数（demo 演示）：?role=parent&kid=0 或 ?role=teacher
     2. 后端 /api/auth/me（钉钉 SSO 后）
     3. 默认：teacher（开发环境/独立浏览器）

   公开 API：
     UserAuth.ready(callback)        // 异步等身份就位
     UserAuth.getRole()              // 'teacher' | 'parent' | 'admin'
     UserAuth.isTeacher()
     UserAuth.isParent()
     UserAuth.getBoundIdx()          // 家长：roster 索引（demo）；老师：null
     UserAuth.getBoundStudent()      // 家长：绑定的学生对象；老师：null
   ═══════════════════════════════════════════════════════════ */
(function(global){
  const STATE = {
    ready: false,
    role: 'teacher',
    subRole: null,            // 'general' (总务) | 'class' (班主任)
    boundIdx: null,
    boundIdCard: null,
    boundStudent: null,
    boundGrade: null,
    boundClass: null,
    kidName: null,            // 家长绑定的孩子真名（例如"陈思麟"），用于按真名过滤
    _callbacks: [],
  };

  function _qs(name){
    const m = location.search.match(new RegExp('[?&]'+name+'=([^&]*)'));
    return m ? decodeURIComponent(m[1]) : null;
  }

  function _emitReady(){
    STATE.ready = true;
    _applyRoleDom();
    STATE._callbacks.splice(0).forEach(cb => { try { cb(); } catch(e){ console.error(e); } });
  }

  /* ── 把 DB 拉回来的 student 行 → 岛屿可消费的"虚拟学生" ── */
  const _LV = {'优秀':'great','良好':'good','及格':'fair','一般':'fair','不及格':'watch','待提升':'watch'};
  function _lvl(v){ return _LV[v] || 'fair'; }
  function _hash(str){ let h=0; for(let i=0;i<(str||'').length;i++){ h=(h*31+str.charCodeAt(i))>>>0; } return h; }
  function _buildStudentVM(stu, kidNameOverride){
    if(!stu) return null;
    const COLORS = ['#7C5BCC','#FF8C42','#22A05B','#E94B6A','#3DB7E2','#FFC23F','#0E5E80','#A893E8'];
    const realName = kidNameOverride || stu.name || '我的孩子';
    const grade = stu.grade_name || '小学';
    const klass = stu.class_name || '';
    const fitArr = Array.isArray(stu.fitness) && stu.fitness.length ? stu.fitness[0] : (stu.total_level ? stu : null);
    const fitness = [
      {name:'50米跑',    status:_lvl(fitArr && fitArr.run_50m_level),   emoji:'🏃'},
      {name:'坐位体前屈', status:_lvl(fitArr && fitArr.sit_reach_level), emoji:'🤸'},
      {name:'跳绳',      status:_lvl(fitArr && fitArr.jump_rope_level),  emoji:'💪'},
      {name:'肺活量',    status:_lvl(fitArr && fitArr.vital_level),      emoji:'🫁'},
      {name:'立定跳远',  status:_lvl(fitArr && fitArr.jump_stand_level), emoji:'🦵'},
      {name:'仰卧起坐',  status:_lvl(fitArr && fitArr.sit_up_level),     emoji:'⏱'},
    ];
    let age = 10;
    if(stu.birth_date){
      const m = /(\d{4})/.exec(stu.birth_date);
      if(m) age = Math.max(6, Math.min(13, (new Date().getFullYear()) - parseInt(m[1],10)));
    }
    const allergies = (stu.allergies || []).map(a => a.allergen || a).filter(Boolean);
    const joined = (stu.clubs || []).map(c => c.club_name || c.name).filter(Boolean);
    return {
      displayName: realName,
      avatar: realName.charAt(0),
      color: COLORS[_hash(realName) % COLORS.length],
      grade: grade, class: klass, age: age,
      intro: '📚 我的孩子',
      fitness: fitness,
      allergy: allergies, special: null,
      interests: [], borrowed: [], joined: joined,
      idCard: stu.id_card,
      _raw: stu,
    };
  }
  async function _fetchBoundStudent(idCard){
    try {
      const r = await fetch('/api/students/' + encodeURIComponent(idCard));
      if(!r.ok) return null;
      const data = await r.json();
      return _buildStudentVM(data, STATE.kidName);
    } catch(e){ return null; }
  }

  /* 扫描 DOM 上的 role 标记，按角色切换文案 / 显隐 / 角色徽章
     支持的属性：
       data-hide-for="parent"          → 当前角色匹配则 display:none
       data-show-for="teacher,admin"   → 当前角色不匹配则 display:none
       data-text-teacher / data-text-parent / data-text-admin → 覆盖文本
       data-html-teacher / data-html-parent → 覆盖 innerHTML
   */
  function _applyRoleDom(){
    const role = STATE.role;
    const matches = (val) => val && val.split(',').map(s=>s.trim()).includes(role);

    document.querySelectorAll('[data-hide-for]').forEach(el => {
      if(matches(el.dataset.hideFor)) el.style.display = 'none';
    });
    document.querySelectorAll('[data-show-for]').forEach(el => {
      if(matches(el.dataset.showFor)) el.style.display = '';     // 命中 → unhide（清掉内联 none）
      else el.style.display = 'none';                            // 不命中 → 隐藏
    });
    // 子角色（仅 teacher 时关心）：general / class
    const sub = STATE.subRole || '';
    const subMatch = (v) => v && v.split(',').map(s=>s.trim()).includes(sub);
    document.querySelectorAll('[data-show-sub]').forEach(el => {
      if(subMatch(el.dataset.showSub)) el.style.display = '';
      else el.style.display = 'none';
    });
    document.querySelectorAll('[data-hide-sub]').forEach(el => {
      if(subMatch(el.dataset.hideSub)) el.style.display = 'none';
    });
    const textKey = 'text' + role.charAt(0).toUpperCase() + role.slice(1);
    document.querySelectorAll('[data-text-teacher],[data-text-parent],[data-text-admin]').forEach(el => {
      const v = el.dataset[textKey];
      if(v != null) el.textContent = v;
    });
    const htmlKey = 'html' + role.charAt(0).toUpperCase() + role.slice(1);
    document.querySelectorAll('[data-html-teacher],[data-html-parent],[data-html-admin]').forEach(el => {
      const v = el.dataset[htmlKey];
      if(v != null) el.innerHTML = v;
    });

    // 顶栏不再插入角色徽章（按用户要求顶栏只显示学生名）
    // 自动刷新 student-pill 显示登录用户身份
    if(global.UserAuth && global.UserAuth.refreshPill){
      try { global.UserAuth.refreshPill(); } catch(e){ /* ignore */ }
    }
  }

  // 是否在钉钉 webview 内
  function _inDingTalk(){
    return /DingTalk/i.test(navigator.userAgent);
  }

  // 等钉钉 bootstrap 完成登录(最多 8s);成功则继续,失败则放行(显示提示)
  function _waitDingTalkSession(timeoutMs){
    return new Promise(resolve => {
      if(sessionStorage.getItem('bs_session_token')) return resolve(true);
      const onLogin = () => { cleanup(); resolve(true); };
      const timer = setTimeout(() => { cleanup(); resolve(!!sessionStorage.getItem('bs_session_token')); }, timeoutMs || 8000);
      function cleanup(){
        window.removeEventListener('bs:logged-in', onLogin);
        clearTimeout(timer);
      }
      window.addEventListener('bs:logged-in', onLogin);
    });
  }

  async function _init(){
    // 0. 钉钉 webview 内:强制等待 sessionToken,不允许 demo 旁路
    if(_inDingTalk()){
      const ok = await _waitDingTalkSession(8000);
      if(ok){
        // 用拿到的 session 去 /api/auth/me 取角色
        try{
          const r = await fetch('/api/auth/me');   // fetch 已被 bootstrap 注入 Bearer
          if(r.ok){
            const data = await r.json();
            STATE.role = data.role || 'parent';
            STATE.subRole = data.subRole || null;
            STATE.boundIdCard = data.boundIdCard || null;
            STATE.boundGrade = data.boundGrade || null;
            STATE.boundClass = data.boundClass || null;
            if(data.boundStudent){ STATE.boundStudent = data.boundStudent; }
            sessionStorage.setItem('bs_role', STATE.role);
            if(STATE.subRole) sessionStorage.setItem('bs_sub_role', STATE.subRole);
            if(STATE.boundGrade) sessionStorage.setItem('bs_bound_grade', STATE.boundGrade);
            if(STATE.boundClass) sessionStorage.setItem('bs_bound_class', STATE.boundClass);
            if(STATE.boundIdCard) sessionStorage.setItem('bs_bound_id_card', STATE.boundIdCard);
            _emitReady();
            return;
          }
        }catch(e){ /* 落到 demo 模式兜底 */ }
      }
      // 钉钉鉴权超时(8s 没拿到 session)→ 退回 demo 模式继续,但留 warning
      console.warn('[UserAuth] 钉钉登录超时,退回默认身份');
    }

    // 未登录 → 跳到登录页(login.html / 公开页面不走这个逻辑)
    const PUBLIC_PAGES = ['login.html', 'island-art.html', 'dashboard.html'];
    if(!sessionStorage.getItem('bs_role') && !_qs('role')){
      const path = location.pathname.split('/').pop();
      if(path && !PUBLIC_PAGES.includes(path) && path !== ''){
        location.replace('login.html');
        return;
      }
    }
    // 1. URL demo 模式
    const urlRole = _qs('role');
    if(urlRole === 'parent' || urlRole === 'teacher' || urlRole === 'admin'){
      STATE.role = urlRole;
      STATE.subRole = _qs('sub') || null;       // teacher 子角色: general / class
      STATE.boundGrade = _qs('grade') || null;
      STATE.boundClass = _qs('class') || null;
      STATE.kidName = _qs('kidName') || null;
      if(urlRole === 'parent'){
        const kid = _qs('kid');
        const idx = parseInt(kid, 10);
        if(!isNaN(idx) && window.StudentRoster){
          STATE.boundIdx = idx;
          STATE.boundStudent = window.StudentRoster.get(idx);
        }
        // 支持直接传 id_card（如 ?role=parent&kid=BS_00841）
        if(isNaN(idx) && kid && kid.length > 4){
          STATE.boundIdCard = kid;
          STATE.boundGrade = _qs('grade') || null;
          STATE.boundClass = _qs('class') || null;
          sessionStorage.setItem('bs_bound_id_card', kid);
          // 异步从 API 拉学生信息补全 boundStudent
          _fetchBoundStudent(kid).then(s => {
            if(s){
              STATE.boundStudent = s;
              try { sessionStorage.setItem('bs_bound_student_json', JSON.stringify(s._raw || s)); } catch(e){}
              _applyRoleDom();
            }
          });
        }
      }
      sessionStorage.setItem('bs_role', STATE.role);
      if(STATE.subRole) sessionStorage.setItem('bs_sub_role', STATE.subRole);
      if(STATE.boundIdx !== null) sessionStorage.setItem('bs_bound_idx', String(STATE.boundIdx));
      if(STATE.boundGrade) sessionStorage.setItem('bs_bound_grade', STATE.boundGrade);
      if(STATE.boundClass) sessionStorage.setItem('bs_bound_class', STATE.boundClass);
      if(STATE.kidName) sessionStorage.setItem('bs_kid_name', STATE.kidName);
      _emitReady();
      return;
    }

    // 2. 从 session 缓存恢复 → 立即生效，不等 /api/auth/me（避免 UI 闪烁）
    const cachedRole = sessionStorage.getItem('bs_role');
    const cachedBoundIdx = sessionStorage.getItem('bs_bound_idx');
    if(cachedRole){
      STATE.role = cachedRole;
      STATE.subRole = sessionStorage.getItem('bs_sub_role') || null;
      STATE.boundGrade = sessionStorage.getItem('bs_bound_grade') || null;
      STATE.boundClass = sessionStorage.getItem('bs_bound_class') || null;
      STATE.kidName = sessionStorage.getItem('bs_kid_name') || null;
      STATE.boundIdCard = sessionStorage.getItem('bs_bound_id_card') || null;
      // 家长：优先读 login.html 预拉到的真实档案
      const cachedStu = sessionStorage.getItem('bs_bound_student_json');
      if(cachedStu){
        try { STATE.boundStudent = _buildStudentVM(JSON.parse(cachedStu), STATE.kidName); }
        catch(e){ /* fall through */ }
      }
      if(cachedBoundIdx !== null){
        STATE.boundIdx = parseInt(cachedBoundIdx, 10);
        if(!STATE.boundStudent && window.StudentRoster) STATE.boundStudent = window.StudentRoster.get(STATE.boundIdx);
      }
      // 缓存没拉到 → 异步补一次
      if(!STATE.boundStudent && STATE.boundIdCard){
        _fetchBoundStudent(STATE.boundIdCard).then(s => {
          if(s){
            STATE.boundStudent = s;
            try { sessionStorage.setItem('bs_bound_student_json', JSON.stringify(s._raw || s)); } catch(e){}
            _applyRoleDom();
          }
        });
      }
      // 立即发布身份就位事件，让 DOM 切换 / 渲染立即用
      _emitReady();
      return;
    }

    // 3. 异步问后端
    try {
      const headers = {};
      const sess = sessionStorage.getItem('bs_session_token');
      if(sess) headers['Authorization'] = 'Bearer ' + sess;
      const r = await fetch('/api/auth/me', { headers });
      if(r.ok){
        const data = await r.json();
        STATE.role = data.role || 'teacher';
        STATE.subRole = data.subRole || null;
        STATE.boundGrade = data.boundGrade || null;
        STATE.boundClass = data.boundClass || null;
        STATE.boundIdCard = data.boundIdCard || data.bound_id_card || null;
        if(data.boundStudent){
          STATE.boundStudent = data.boundStudent;
        }
        sessionStorage.setItem('bs_role', STATE.role);
        if(STATE.subRole) sessionStorage.setItem('bs_sub_role', STATE.subRole);
        if(STATE.boundGrade) sessionStorage.setItem('bs_bound_grade', STATE.boundGrade);
        if(STATE.boundClass) sessionStorage.setItem('bs_bound_class', STATE.boundClass);
        if(STATE.boundIdCard) sessionStorage.setItem('bs_bound_id_card', STATE.boundIdCard);
      }
    } catch(e){
      // 后端不可用 → 静默使用默认 teacher
    }
    // 公开页面:未认证时用 visitor 角色,不暴露教师控件
    if(PUBLIC_PAGES.includes(location.pathname.split('/').pop())){
      const hasSession = sessionStorage.getItem('bs_session_token');
      const hasRole = sessionStorage.getItem('bs_role');
      if(!hasSession && !hasRole){
        STATE.role = 'public';
      }
    }
    _emitReady();
    // 二次确保：async auth 完成后重新匹配 DOM
    _applyRoleDom();
  }

  global.UserAuth = {
    ready(cb){ STATE.ready ? cb() : STATE._callbacks.push(cb); },
    getRole(){ return STATE.role; },
    getSubRole(){ return STATE.subRole; },
    isTeacher(){ return STATE.role === 'teacher' || STATE.role === 'admin'; },
    isGeneralTeacher(){ return (STATE.role === 'teacher' && STATE.subRole === 'general') || STATE.role === 'admin'; },
    isClassTeacher(){ return STATE.role === 'teacher' && STATE.subRole === 'class'; },
    isParent(){ return STATE.role === 'parent'; },
    getBoundIdx(){ return STATE.boundIdx; },
    getBoundStudent(){ return STATE.boundStudent; },
    getBoundIdCard(){ return STATE.boundIdCard; },
    getBoundGrade(){ return STATE.boundGrade; },
    getBoundClass(){ return STATE.boundClass; },
    getKidName(){ return STATE.kidName; },
    getDisplayName(){ return sessionStorage.getItem('bs_user_nick') || ''; },
    /** 把顶栏的 student-pill 改成显示当前登录用户身份（老师→老师名+角色；家长→孩子名） */
    refreshPill(pillEl){
      pillEl = pillEl || document.querySelector('.student-pill');
      if(!pillEl) return;
      const avatar = pillEl.querySelector('.stu-avatar') || pillEl.querySelector('#homeStuAvatar');
      const nameEl = pillEl.querySelector('.name') || pillEl.querySelector('#homeStuName');
      const metaEl = pillEl.querySelector('.meta') || pillEl.querySelector('#homeStuMeta');
      if(!avatar || !nameEl || !metaEl) return;
      const nick = STATE.role && (sessionStorage.getItem('bs_user_nick') || '');
      if(STATE.role === 'parent'){
        const kid = STATE.kidName || (STATE.boundStudent && STATE.boundStudent.displayName) || '我的孩子';
        avatar.textContent = kid.charAt(0);
        avatar.style.background = 'linear-gradient(135deg,#FF8E9C,#E94B6A)';
        nameEl.textContent = kid;
        metaEl.textContent = nick && nick.replace(kid,'') || '家长账号';
      } else if(STATE.subRole === 'general'){
        avatar.textContent = '总';
        avatar.style.background = 'linear-gradient(135deg,#FFD86A,#FF9F4A)';
        nameEl.textContent = nick || '总务老师';
        metaEl.textContent = '总务老师';
      } else if(STATE.subRole === 'class'){
        avatar.textContent = '班';
        avatar.style.background = 'linear-gradient(135deg,#76C342,#22A05B)';
        nameEl.textContent = nick || '班主任';
        const tag = [STATE.boundGrade, STATE.boundClass].filter(Boolean).join(' ');
        metaEl.textContent = tag || '班主任';
      } else if(STATE.role === 'teacher' || STATE.role === 'admin'){
        avatar.textContent = '师';
        avatar.style.background = 'linear-gradient(135deg,#5BC8E8,#0E5E80)';
        nameEl.textContent = nick || '老师';
        metaEl.textContent = '老师';
      } else if(STATE.role === 'public'){
        // 公开访问:不修改 DOM,保留页面默认值(张老师/策展人)
        return;
      }
    },
    /** 清掉所有 session 身份，跳回登录页 */
    signOut(){
      ['bs_role','bs_sub_role','bs_bound_idx','bs_bound_id_card','bs_bound_student_json','bs_bound_grade','bs_bound_class','bs_kid_name','bs_session_token','bs_user_nick','bs_user_avatar'].forEach(k => sessionStorage.removeItem(k));
      location.href = 'login.html';
    },
    /** 写入身份并就地刷新，让所有岛屿生效 */
    signIn(opts){
      const { role, subRole, boundIdx, boundGrade, boundClass, kidName } = opts || {};
      if(!role) return false;
      sessionStorage.setItem('bs_role', role);
      if(subRole)    sessionStorage.setItem('bs_sub_role', subRole);    else sessionStorage.removeItem('bs_sub_role');
      if(boundGrade) sessionStorage.setItem('bs_bound_grade', boundGrade); else sessionStorage.removeItem('bs_bound_grade');
      if(boundClass) sessionStorage.setItem('bs_bound_class', boundClass); else sessionStorage.removeItem('bs_bound_class');
      if(kidName)    sessionStorage.setItem('bs_kid_name', kidName);    else sessionStorage.removeItem('bs_kid_name');
      if(boundIdx != null) sessionStorage.setItem('bs_bound_idx', String(boundIdx)); else sessionStorage.removeItem('bs_bound_idx');
      return true;
    },
  };

  // DOMContentLoaded 之前/之后都允许调用 ready()
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }
})(window);
