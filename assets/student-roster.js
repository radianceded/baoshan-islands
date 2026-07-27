/* ═══════════════════════════════════════════════════════════
   宝山实验 · 4 名演示学生的统一数据
   供 island-health / island-reading / island-activity 共享使用
   每页保存当前学生索引 currentStudentIdx，切换时更新 UI + AI 上下文
   ═══════════════════════════════════════════════════════════ */
(function(global){
  const STATUS_MAP = {good:'良好', fair:'一般', watch:'待提升', great:'优秀'};

  /* ROSTER 已迁到 DB：家长账号绑定到真实 students.id_card
     登录时 login.html 会预拉 /api/students/<bound_id_card> 并缓存进 sessionStorage
     UserAuth 把它构造成学生 VM；这里读 UserAuth.getBoundStudent() */
  const ROSTER = [];

  /* ── 全局：当前选中的学生（仅 session 内持久化，关闭浏览器会回默认） ── */
  const CURRENT_IDX_KEY = 'bs_current_student_idx';
  function _store(){ return (typeof sessionStorage !== 'undefined') ? sessionStorage : null; }
  function getCurrentIdx(){
    // 家长强制锁到自己孩子
    if(window.UserAuth && window.UserAuth.isParent && window.UserAuth.isParent()){
      const b = window.UserAuth.getBoundIdx();
      if(typeof b === 'number' && b >= 0 && b < size()) return b;
    }
    const s = _store();
    if(!s) return 0;
    const v = parseInt(s.getItem(CURRENT_IDX_KEY) || '0', 10);
    if(isNaN(v) || v < 0 || v >= size()) return 0;
    return v;
  }
  function setCurrentIdx(idx){
    // 家长账号不允许修改
    if(window.UserAuth && window.UserAuth.isParent && window.UserAuth.isParent()) return;
    if(typeof idx !== 'number' || idx < 0) idx = 0;
    const s = _store();
    if(s) s.setItem(CURRENT_IDX_KEY, String(idx));
  }
  // 清理一次旧的 localStorage 残留（之前版本写错地方了）
  try { localStorage.removeItem(CURRENT_IDX_KEY); } catch(e){}

  /* ── 自定义学生（持久化到 localStorage） ── */
  const CUSTOM_KEY = 'bs_custom_students';
  function loadCustom(){
    try { return JSON.parse(localStorage.getItem(CUSTOM_KEY) || '[]'); }
    catch(e){ return []; }
  }
  function saveCustom(arr){ localStorage.setItem(CUSTOM_KEY, JSON.stringify(arr)); }
  function allRoster(){ return ROSTER.concat(loadCustom()); }

  function get(idx){
    // 家长：永远返回 UserAuth 缓存的真实学生（idx 忽略）
    if(window.UserAuth && window.UserAuth.isParent && window.UserAuth.isParent()){
      const bound = window.UserAuth.getBoundStudent && window.UserAuth.getBoundStudent();
      if(bound) return bound;
    }
    const all = allRoster();
    if(!all.length) return null;
    return all[Math.max(0, idx|0) % all.length];
  }
  function size(){
    if(window.UserAuth && window.UserAuth.isParent && window.UserAuth.isParent()){
      return window.UserAuth.getBoundStudent && window.UserAuth.getBoundStudent() ? 1 : 0;
    }
    return allRoster().length;
  }

  function addCustomStudent(data){
    const arr = loadCustom();
    arr.push(Object.assign({ _custom:true, _id:'c_'+Date.now() }, data));
    saveCustom(arr);
    return arr[arr.length-1];
  }
  function removeCustomStudent(id){
    const arr = loadCustom().filter(s => s._id !== id);
    saveCustom(arr);
  }

  function studentInfoBlock(s){
    return `- 姓名（脱敏）：${s.displayName}
- 年级班级：${s.grade} ${s.class}
- 年龄：${s.age} 岁`;
  }

  function fitnessBlock(s){
    return s.fitness.map(f => `- ${f.name}：${STATUS_MAP[f.status]||f.status}`).join('\n');
  }

  function weakItems(s){
    return s.fitness.filter(f=>f.status==='watch'||f.status==='fair').map(f=>f.name);
  }

  function _injectPickerStyles(){
    if(document.getElementById('roster-picker-styles')) return;
    const css = `
      .sr-picker-wrap{position:relative;display:inline-block}
      .sr-picker-panel{
        position:absolute;top:calc(100% + 8px);right:0;z-index:100;
        background:#fff;border-radius:18px;box-shadow:0 16px 40px rgba(0,30,60,.18);
        padding:8px;min-width:300px;max-height:80vh;overflow:auto;
        opacity:0;transform:translateY(-6px) scale(.96);
        pointer-events:none;transition:opacity .18s, transform .22s cubic-bezier(.34,1.56,.64,1);
        border:1.5px solid rgba(180,220,240,.6);
      }
      .sr-picker-panel.open{opacity:1;transform:translateY(0) scale(1);pointer-events:auto}
      .sr-picker-item{
        display:flex;align-items:center;gap:12px;
        padding:10px 12px;border-radius:12px;cursor:pointer;
        transition:background .12s;position:relative;
      }
      .sr-picker-item:hover{background:#F4FAFD}
      .sr-picker-item.active{background:linear-gradient(135deg,rgba(124,91,204,.08),rgba(91,200,232,.08))}
      .sr-picker-item.active .sr-tick{display:flex}
      .sr-tick{display:none;position:absolute;right:12px;top:50%;transform:translateY(-50%);width:18px;height:18px;border-radius:50%;background:#22A05B;color:#fff;align-items:center;justify-content:center;font-size:11px;font-weight:900}
      .sr-del{position:absolute;right:12px;top:50%;transform:translateY(-50%);width:22px;height:22px;border-radius:50%;background:#FFE0E0;color:#C2410C;border:none;font-size:12px;cursor:pointer;display:none}
      .sr-picker-item:hover .sr-del{display:inline-flex;align-items:center;justify-content:center}
      .sr-picker-item.active:hover .sr-tick{display:none}
      .sr-picker-av{
        width:40px;height:40px;border-radius:50%;
        color:#fff;font-weight:900;font-size:17px;
        display:flex;align-items:center;justify-content:center;flex-shrink:0;
        box-shadow:0 3px 8px rgba(0,30,60,.15);
      }
      .sr-picker-meta{flex:1;min-width:0}
      .sr-picker-meta .nm{font-size:13.5px;font-weight:800;color:#1F3A4D;letter-spacing:.5px;display:flex;align-items:center;gap:6px}
      .sr-picker-meta .nm .tag{font-size:9px;font-weight:800;background:#FFF3D0;color:#C2410C;padding:1px 6px;border-radius:6px;letter-spacing:.5px}
      .sr-picker-meta .gr{font-size:11px;color:#7BB8DA;font-weight:700;margin-top:1px}
      .sr-picker-meta .it{font-size:11.5px;color:#5C7A8C;font-weight:600;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:230px}
      .sr-picker-add{
        margin-top:6px;padding:10px 12px;border-radius:12px;border:1.5px dashed #B0D8F0;
        text-align:center;font-size:13px;font-weight:800;color:#0E5E80;
        cursor:pointer;transition:all .15s;background:#F4FAFD;
      }
      .sr-picker-add:hover{background:#E0F2FF;border-color:#7BB8DA;color:#0E5E80}

      /* 表单弹窗 */
      .sr-add-veil{position:fixed;inset:0;background:rgba(0,30,60,.55);z-index:300;display:none;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(4px)}
      .sr-add-veil.open{display:flex}
      .sr-add-modal{background:#fff;border-radius:22px;width:480px;max-width:100%;max-height:90vh;overflow:auto;padding:24px;box-shadow:0 24px 60px rgba(0,30,60,.3);animation:srPop .35s cubic-bezier(.34,1.56,.64,1)}
      @keyframes srPop{from{transform:scale(.7);opacity:0}to{transform:scale(1);opacity:1}}
      .sr-add-modal h3{font-size:20px;font-weight:900;color:#1F3A4D;letter-spacing:2px;margin-bottom:16px;display:flex;align-items:center;gap:8px}
      .sr-form-row{margin-bottom:12px}
      .sr-form-row label{display:block;font-size:12px;color:#5C7A8C;font-weight:700;margin-bottom:5px;letter-spacing:.5px}
      .sr-form-row input, .sr-form-row select{
        width:100%;padding:9px 12px;border:1.5px solid #DCEBF3;border-radius:10px;font-size:13.5px;
        color:#1F3A4D;outline:none;background:#F4FAFD;font-family:inherit;
      }
      .sr-form-row input:focus, .sr-form-row select:focus{border-color:#5BC8E8;background:#fff}
      .sr-form-row .hint{font-size:10.5px;color:#7BB8DA;margin-top:3px;font-weight:600}
      .sr-form-2col{display:grid;grid-template-columns:1fr 1fr;gap:10px}
      .sr-form-3col{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
      .sr-fit-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
      .sr-fit-item{display:flex;align-items:center;gap:8px;background:#F4FAFD;padding:6px 10px;border-radius:10px}
      .sr-fit-item label{font-size:12px;font-weight:700;color:#1F3A4D;margin:0;flex:1;letter-spacing:0}
      .sr-fit-item select{padding:3px 6px;font-size:11px;border:1px solid #DCEBF3;border-radius:6px;background:#fff;width:auto}
      .sr-color-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
      .sr-color-dot{width:28px;height:28px;border-radius:50%;cursor:pointer;border:2.5px solid transparent;transition:transform .15s}
      .sr-color-dot:hover{transform:scale(1.1)}
      .sr-color-dot.selected{border-color:#1F3A4D;transform:scale(1.1)}
      .sr-add-actions{margin-top:18px;display:flex;gap:10px;justify-content:flex-end}
      .sr-btn{font-weight:800;font-size:13.5px;letter-spacing:1px;border:none;border-radius:14px;padding:10px 18px;cursor:pointer;font-family:inherit}
      .sr-btn.primary{background:linear-gradient(135deg,#5BC8E8,#0E5E80);color:#fff;box-shadow:0 4px 12px rgba(14,94,128,.3)}
      .sr-btn.ghost{background:#F4FAFD;color:#5C7A8C}
    `;
    const s = document.createElement('style');
    s.id = 'roster-picker-styles';
    s.textContent = css;
    document.head.appendChild(s);
  }

  const COLORS = ['#7C5BCC','#FF8C42','#22A05B','#E94B6A','#3DB7E2','#FFC23F','#0E5E80','#A893E8','#FF6B6B','#76C342'];
  const FIT_DEFAULTS = [
    {name:'50米跑',     emoji:'🏃'},
    {name:'坐位体前屈', emoji:'🤸'},
    {name:'跳绳',       emoji:'💪'},
    {name:'肺活量',     emoji:'🫁'},
    {name:'耐力跑',     emoji:'⏱'},
    {name:'立定跳远',   emoji:'🦵'},
  ];

  function _openAddForm(onSaved){
    let veil = document.getElementById('sr-add-veil');
    if(veil) veil.remove();
    veil = document.createElement('div');
    veil.id = 'sr-add-veil';
    veil.className = 'sr-add-veil';
    veil.innerHTML = `
      <div class="sr-add-modal" onclick="event.stopPropagation()">
        <h3>🧒 添加自定义学生</h3>
        <div class="sr-form-row">
          <label>姓名（已脱敏） *</label>
          <input id="sr-name" placeholder="如：刘**" maxlength="20">
          <div class="hint">建议姓后接 ** 形式，保护隐私</div>
        </div>
        <div class="sr-form-2col">
          <div class="sr-form-row">
            <label>头像字 *</label>
            <input id="sr-avatar" placeholder="如：刘" maxlength="1">
          </div>
          <div class="sr-form-row">
            <label>年龄 *</label>
            <input id="sr-age" type="number" min="6" max="13" value="10">
          </div>
        </div>
        <div class="sr-form-2col">
          <div class="sr-form-row">
            <label>年级 *</label>
            <select id="sr-grade">
              <option>小学</option>
            </select>
          </div>
          <div class="sr-form-row">
            <label>班级 *</label>
            <input id="sr-class" placeholder="如：五年级 2 班">
          </div>
        </div>
        <div class="sr-form-row">
          <label>主题色</label>
          <div class="sr-color-row" id="sr-color-row"></div>
        </div>
        <div class="sr-form-row">
          <label>一句话介绍（10-20 字）</label>
          <input id="sr-intro" placeholder="如：🎨 喜欢画画 · 运动小天才" maxlength="30">
        </div>
        <div class="sr-form-row">
          <label>兴趣偏好（用、分隔）</label>
          <input id="sr-interests" placeholder="如：科幻、画画、足球">
        </div>
        <div class="sr-form-row">
          <label>过敏原（可选，用、分隔）</label>
          <input id="sr-allergy" placeholder="如：花生、鸡蛋">
        </div>
        <div class="sr-form-row">
          <label>体测情况</label>
          <div class="sr-fit-grid" id="sr-fit-grid"></div>
        </div>
        <div class="sr-add-actions">
          <button class="sr-btn ghost" id="sr-cancel">取消</button>
          <button class="sr-btn primary" id="sr-save">✓ 保存</button>
        </div>
      </div>
    `;
    document.body.appendChild(veil);
    // 让弹窗可见（CSS 默认 display:none，加上 .open 才显示）
    requestAnimationFrame(()=> veil.classList.add('open'));
    // 颜色选择
    let pickedColor = COLORS[0];
    const cRow = veil.querySelector('#sr-color-row');
    cRow.innerHTML = COLORS.map((c,i)=>`<span class="sr-color-dot ${i===0?'selected':''}" data-color="${c}" style="background:${c}"></span>`).join('');
    cRow.querySelectorAll('.sr-color-dot').forEach(el=>{
      el.addEventListener('click', ()=>{
        cRow.querySelectorAll('.sr-color-dot').forEach(x=>x.classList.remove('selected'));
        el.classList.add('selected');
        pickedColor = el.dataset.color;
      });
    });
    // 体测：6 项 select
    const fitGrid = veil.querySelector('#sr-fit-grid');
    fitGrid.innerHTML = FIT_DEFAULTS.map((f,i)=>`
      <div class="sr-fit-item">
        <label>${f.emoji} ${f.name}</label>
        <select data-i="${i}">
          <option value="great">优秀</option>
          <option value="good">良好</option>
          <option value="fair" selected>一般</option>
          <option value="watch">待提升</option>
        </select>
      </div>
    `).join('');
    // 自动从姓名提取头像
    veil.querySelector('#sr-name').addEventListener('input', e=>{
      const av = veil.querySelector('#sr-avatar');
      if(!av.value && e.target.value) av.value = e.target.value.charAt(0);
    });
    // 关闭
    veil.addEventListener('click', e=>{ if(e.target===veil) veil.remove(); });
    veil.querySelector('#sr-cancel').addEventListener('click', ()=>veil.remove());
    // 保存
    veil.querySelector('#sr-save').addEventListener('click', ()=>{
      const name = veil.querySelector('#sr-name').value.trim();
      const avatar = veil.querySelector('#sr-avatar').value.trim();
      const klass = veil.querySelector('#sr-class').value.trim();
      if(!name || !avatar || !klass){
        alert('姓名、头像字、班级必填');
        return;
      }
      const data = {
        displayName: name,
        avatar: avatar.charAt(0),
        color: pickedColor,
        grade: veil.querySelector('#sr-grade').value,
        class: klass,
        age: parseInt(veil.querySelector('#sr-age').value, 10) || 10,
        intro: veil.querySelector('#sr-intro').value.trim() || '✨ 自定义学生',
        interests: (veil.querySelector('#sr-interests').value || '').split(/[、,，\s]+/).filter(Boolean),
        allergy: (veil.querySelector('#sr-allergy').value || '').split(/[、,，\s]+/).filter(Boolean),
        special: null,
        fitness: FIT_DEFAULTS.map((f,i)=>({
          name: f.name, emoji: f.emoji,
          status: veil.querySelector(`#sr-fit-grid select[data-i="${i}"]`).value
        })),
        borrowed: [],
        joined: [],
      };
      const saved = addCustomStudent(data);
      veil.remove();
      if(typeof onSaved === 'function') onSaved(saved);
    });
  }

  function _isParentLocked(){
    return window.UserAuth && window.UserAuth.isParent && window.UserAuth.isParent();
  }

  /* 把现有的 .student-pill 改造成"点击展开下拉、选人切换"
     opts = { initialIdx:0, onChange:(idx,student)=>{} } */
  function attachPicker(pillEl, opts){
    if(!pillEl) return;
    opts = opts || {};
    _injectPickerStyles();

    // 老师 / 管理员：不绑学生，pill 已由 UserAuth.refreshPill() 渲染为老师身份
    if(window.UserAuth && window.UserAuth.isTeacher && window.UserAuth.isTeacher()){
      pillEl.style.cursor = 'default';
      pillEl.title = '老师账号';
      return { setActive(){}, open(){}, close(){}, toggle(){} };
    }

    // 家长锁定模式：禁掉下拉，只显示锁住的孩子，加个 "🔒 我的孩子" 角标
    if(_isParentLocked()){
      pillEl.style.cursor = 'default';
      pillEl.title = '家长账号 · 只能查看自己的孩子';
      if(!pillEl.querySelector('.sr-parent-badge')){
        const tag = document.createElement('span');
        tag.className = 'sr-parent-badge';
        tag.textContent = '🔒 我的孩子';
        tag.style.cssText = 'font-size:10px;font-weight:800;background:#FFF3D0;color:#C2410C;padding:2px 8px;border-radius:8px;margin-left:6px';
        pillEl.appendChild(tag);
      }
      return { setActive(){}, open(){}, close(){}, toggle(){} };
    }

    // 包装一层，让 panel 相对 pill 定位
    const parent = pillEl.parentElement;
    if(!parent.classList.contains('sr-picker-wrap')){
      const wrap = document.createElement('div');
      wrap.className = 'sr-picker-wrap';
      parent.insertBefore(wrap, pillEl);
      wrap.appendChild(pillEl);
    }
    const wrap = pillEl.parentElement;

    // 构建下拉
    const panel = document.createElement('div');
    panel.className = 'sr-picker-panel';
    // 优先用持久化的值，再退到 opts.initialIdx，再退到 0
    let activeIdx = (opts.initialIdx !== undefined ? opts.initialIdx : getCurrentIdx());
    if(activeIdx >= size()) activeIdx = 0;

    function rebuild(){
      const all = allRoster();
      panel.innerHTML = all.map((s, i)=>`
        <div class="sr-picker-item ${i===activeIdx?'active':''}" data-idx="${i}">
          <div class="sr-picker-av" style="background:linear-gradient(135deg,${s.color},#3DB7E2)">${s.avatar}</div>
          <div class="sr-picker-meta">
            <div class="nm">${s.displayName}${s._custom?' <span class="tag">我</span>':''}</div>
            <div class="gr">${s.grade} · ${s.class} · ${s.age}岁</div>
            <div class="it">${s.intro || ''}</div>
          </div>
          <span class="sr-tick">✓</span>
          ${s._custom ? `<button class="sr-del" data-del="${s._id}" title="删除">×</button>` : ''}
        </div>
      `).join('') + `<div class="sr-picker-add" id="sr-add-btn">+ 添加自定义学生</div>`;

      panel.querySelectorAll('.sr-picker-item').forEach(el=>{
        el.addEventListener('click', e=>{
          e.stopPropagation();
          const idx = parseInt(el.dataset.idx, 10);
          if(idx === activeIdx){ close(); return; }
          activeIdx = idx;
          setCurrentIdx(idx);   // 持久化
          rebuild();
          close();
          if(typeof opts.onChange === 'function') opts.onChange(idx, allRoster()[idx]);
        });
      });
      panel.querySelectorAll('.sr-del').forEach(btn=>{
        btn.addEventListener('click', e=>{
          e.stopPropagation();
          const id = btn.dataset.del;
          if(!confirm('确定删除这个自定义学生吗？')) return;
          // 如果当前选中的就是被删的，回到 0
          const cur = allRoster()[activeIdx];
          removeCustomStudent(id);
          if(cur && cur._id === id){
            activeIdx = 0;
            setCurrentIdx(0);
            if(typeof opts.onChange === 'function') opts.onChange(0, allRoster()[0]);
          } else {
            // 重新计算 activeIdx（位置可能变了）
            const newAll = allRoster();
            const newIdx = newAll.findIndex(s => s.displayName === cur.displayName && s._id === cur._id);
            activeIdx = newIdx >= 0 ? newIdx : 0;
            setCurrentIdx(activeIdx);
          }
          rebuild();
        });
      });
      panel.querySelector('#sr-add-btn').addEventListener('click', e=>{
        e.stopPropagation();
        close();
        _openAddForm((saved)=>{
          // 新增成功 → 选中新学生
          const newAll = allRoster();
          const newIdx = newAll.length - 1;
          activeIdx = newIdx;
          setCurrentIdx(newIdx);   // 持久化
          rebuild();
          if(typeof opts.onChange === 'function') opts.onChange(newIdx, saved);
        });
      });
    }

    function open(){ panel.classList.add('open'); }
    function close(){ panel.classList.remove('open'); }
    function toggle(){ panel.classList.contains('open') ? close() : open(); }

    rebuild();
    wrap.appendChild(panel);

    pillEl.style.cursor = 'pointer';
    pillEl.title = '点击切换学生';
    pillEl.addEventListener('click', e=>{
      e.stopPropagation();
      toggle();
    });
    document.addEventListener('click', e=>{
      if(!wrap.contains(e.target)) close();
    });
    document.addEventListener('keydown', e=>{
      if(e.key === 'Escape') close();
    });

    return { open, close, toggle, setActive(idx){ activeIdx = idx; rebuild(); } };
  }

  global.StudentRoster = { get, size, studentInfoBlock, fitnessBlock, weakItems, STATUS_MAP, attachPicker, ROSTER, allRoster, addCustomStudent, removeCustomStudent, getCurrentIdx, setCurrentIdx };
})(window);
