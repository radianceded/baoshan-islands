/**
 * StudentModule - 学生管理模块
 * 从 hongkou_v4.html 提取的学生相关功能
 */

const StudentModule = (function() {
    'use strict';

    // ══════════════════════════════════════════════════════
    //  私有变量
    // ══════════════════════════════════════════════════════
    let _currentTab = 'health';
    const _aiGenerated = {};
    let _editingStudentId = null;
    let _deletingStudentId = null;
    let _gradeFilter = 'all';
    let _allergyOnly = false;

    const STATUS_MAP = { good: '良好', fair: '一般', watch: '待提升', great: '优秀' };
    const STATUS_CSS = { good: 'fs-good', fair: 'fs-fair', watch: 'fs-watch', great: 'fs-great' };

    const MEAL_NUTRITION = {
        A: { name: '红烧肉饭套餐', cal: 680, protein: 28, carbs: 85, fat: 22, fiber: 5, iron: 3.8, calcium: 72, zinc: 3.2,
            items: [
                { n: '红烧猪肉', tags: ['大豆', '小麦'], note: '饱和脂肪较高' },
                { n: '清炒花生米', tags: ['花生'], note: '含花生过敏原' },
                { n: '白米饭', tags: [], note: '主要热量来源' },
                { n: '紫菜蛋花汤', tags: ['鸡蛋'], note: '碘·维生素B12' },
                { n: '时令蔬菜', tags: [], note: '膳食纤维' }
            ]
        },
        B: { name: '清蒸鱼柳饭套餐', cal: 520, protein: 34, carbs: 70, fat: 10, fiber: 8, iron: 5.6, calcium: 138, zinc: 2.4,
            items: [
                { n: '清蒸龙利鱼柳', tags: ['鱼类'], note: '优质蛋白·omega-3·低脂' },
                { n: '西蓝花·胡萝卜', tags: [], note: '维生素C·K·β胡萝卜素' },
                { n: '白米饭', tags: [], note: '主要热量来源' },
                { n: '冬瓜排骨汤', tags: [], note: '钙·锌·胶原蛋白' },
                { n: '苹果', tags: [], note: '膳食纤维·维生素C' }
            ]
        }
    };

    // 学生营养数据
    const STUDENT_NUTR = {
        xu: { focus: ['iron', 'calcium', 'protein'], fitness_weak: ['柔韧性', '上肢力量', '立定跳远'],
            nutr_tip: '铁质不足影响肌肉耐力；钙质对骨骼密度尤为重要', rec: 'B',
            lunch_reason: 'B餐铁质(5.6mg)和钙质(138mg)均显著优于A餐，鱼类优质蛋白有助上肢肌力提升，同时完全规避花生过敏原。',
            dinner: [
                { dish: '芹菜炒牛柳', reason: '牛肉富含铁质和优质蛋白，助力肌肉发育', nuts: '铁 4mg', icon: '🥩' },
                { dish: '紫菜虾皮豆腐汤', reason: '虾皮和豆腐都是钙质来源，强化骨骼', nuts: '钙 180mg', icon: '🍲' },
                { dish: '清炒西蓝花', reason: '维生素C促进铁吸收，膳食纤维助消化', nuts: '维C 60mg', icon: '🥦' },
                { dish: '小米南瓜粥', reason: '易消化的优质碳水，补充能量', nuts: '碳水 35g', icon: '🥣' }
            ]
        },
        ming: { focus: ['vitC', 'fiber', 'protein'], fitness_weak: ['视力', '体重管理'],
            nutr_tip: '维生素C和膳食纤维有助于控制体重；注意护眼', rec: 'B',
            lunch_reason: 'B餐热量更低(520kcal)，脂肪含量仅为A餐的45%，有助于体重管理；搭配富含维C的苹果和西蓝花。',
            dinner: [
                { dish: '清蒸鲈鱼', reason: '优质蛋白且低脂，适合体重管理', nuts: '蛋白 18g', icon: '🐟' },
                { dish: '胡萝卜玉米汤', reason: 'β-胡萝卜素有益视力', nuts: '维A 400μg', icon: '🥕' },
                { dish: '凉拌黄瓜', reason: '低热量高纤维，饱腹感强', nuts: '纤维 2g', icon: '🥒' },
                { dish: '杂粮饭', reason: '低GI主食，血糖平稳', nuts: '碳水 40g', icon: '🍚' }
            ]
        }
    };

    // AI内容数据
    const AI_CONTENT = {
        fitness: {
            xu: [
                { label: '整体状况', color: 'green', text: '雨萱的心肺功能和耐力表现突出，日常运动习惯很好，值得继续坚持。' },
                { label: '重点关注', color: 'amber', text: '柔韧性仍需提升，建议每天进行5-10分钟的拉伸训练，尤其是下肢后侧肌群。' },
                { label: '运动建议', color: 'blue', text: '结合喜欢的音乐，可尝试舞蹈类活动或瑜伽，既能提升柔韧性又充满乐趣。' },
                { label: '日常提示', color: 'teal', text: '注意对花生的过敏，学校B餐已自动避开花生类菜品，家长晚餐也请注意。' }
            ],
            ming: [
                { label: '整体状况', color: 'amber', text: '子墨整体体能中等，耐力项目有提升空间，建议循序渐进增加运动量。' },
                { label: '重点关注', color: 'amber', text: '视力保护和体重管理是本学期的重点，减少屏幕时间，增加户外活动。' },
                { label: '运动建议', color: 'blue', text: '对编程感兴趣，可尝试机器人社团或编程相关的动手活动，动眼动脑结合。' },
                { label: '日常提示', color: 'teal', text: '海鲜过敏需注意，建议家长准备午餐时仔细阅读食材标签。' }
            ]
        },
        canteen: {
            xu: { recommend: 'B', reason: 'B餐铁质和钙质更高，鱼类蛋白有助肌力提升，且完全规避花生过敏原。', warn: '' },
            ming: { recommend: 'B', reason: 'B餐热量更低、维C丰富，适合体重管理，且无海鲜类食材。', warn: '' }
        },
        activity: {
            xu: [
                { name: '合唱团', emoji: '🎵', when: '每周二、四 15:30-17:00', reason: '符合「音乐」兴趣，团队活动培养协作能力' },
                { name: '田径社团', emoji: '🏃', when: '每周一、三 16:00-17:30', reason: '利用耐力优势，系统训练可进一步提升体能' }
            ],
            ming: [
                { name: '编程社团', emoji: '💻', when: '每周三 15:30-17:00', reason: '符合「编程」兴趣，培养逻辑思维' },
                { name: '美术社团', emoji: '🎨', when: '每周五 15:30-17:00', reason: '结合「绘画」兴趣，动手创作放松眼睛' }
            ]
        },
        reading: {
            xu: [
                { t: '夏洛的网', a: 'E.B.怀特', bg: '#C8720A', spine: '夏', reason: '经典成长故事，符合阅读兴趣' },
                { t: '昆虫记', a: '法布尔', bg: '#1E5C3A', spine: '虫', reason: '自然科学入门，培养观察力' }
            ],
            ming: [
                { t: '编程真好玩', a: 'DK出版', bg: '#2563EB', spine: '编', reason: '结合编程兴趣的入门书籍' },
                { t: '不一样的卡梅拉', a: '约里波瓦', bg: '#DC2626', spine: '卡', reason: '趣味故事，培养阅读习惯' }
            ]
        }
    };

    const AI_CONFIG = {
        provider: 'baidu',
        baidu: {
            apiKey: ''  // key 已移至服务端，不再硬编码,
            baseUrl: 'https://qianfan.baidubce.com/v2',
            model: 'ernie-5.0-thinking-preview-8k'
        },
        siliconflow: {
            apiKey: 'YOUR_API_KEY_HERE',
            baseUrl: 'https://api.siliconflow.cn/v1',
            model: 'Qwen/Qwen2.5-7B-Instruct'
        },
        useMockData: false
    };

    // ══════════════════════════════════════════════════════
    //  初始化
    // ══════════════════════════════════════════════════════
    function init() {
        if (typeof Store !== 'undefined') {
            Store.subscribe('students', onStudentsChange);
            Store.subscribe('currentStudent', onStudentChange);
        }
    }

    function onStudentsChange() { renderList(); }
    function onStudentChange(student) { if (student) {renderDetail(student);} }

    // ══════════════════════════════════════════════════════
    //  学生列表
    // ══════════════════════════════════════════════════════
    function getFilteredStudents() {
        const students = Store.getStudents ? Store.getStudents() : [];
        const searchEl = document.getElementById('student-search');
        const q = (searchEl && searchEl.value || '').toLowerCase();
        return students.filter(s => {
            const matchGrade = _gradeFilter === 'all' || s.grade === _gradeFilter;
            const matchAllergy = !_allergyOnly || (s.allergy && s.allergy.length > 0);
            const dn = getDisplayName(s);
            const matchQ = !q || (s.name && s.name.toLowerCase().includes(q)) || dn.toLowerCase().includes(q) || (s.no && s.no.toLowerCase().includes(q));
            return matchGrade && matchAllergy && matchQ;
        });
    }

    function getDisplayName(student) {
        if (!student) {return '';}
        if (student.displayName) {return student.displayName;}
        if (typeof Anonymizer !== 'undefined') {return Anonymizer.maskName(student.name);}
        return student.name;
    }

    function renderList() {
        const list = getFilteredStudents();
        const tbody = document.getElementById('student-tbody');
        if (!tbody) {return;}
        tbody.innerHTML = list.map(s => {
            const dn = getDisplayName(s);
            const ab = s.allergy && s.allergy.length > 0 ? s.allergy.map(a => `<span class="atag atag-red" style="margin:1px">${a}</span>`).join('') : '<span class="badge b-gray">无记录</span>';
            const tg = (s.tags || []).map(t => `<span class="badge b-outline" style="margin:1px">${t}</span>`).join('');
            return `<tr style="cursor:pointer" onclick="StudentModule.openDetail('${s.id}')"><td><div style="display:flex;align-items:center;gap:8px"><div style="width:28px;height:28px;border-radius:50%;background:${s.color};color:white;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0">${s.avatar}</div><span class="bold">${dn}</span></div></td><td class="mono">${s.no}</td><td>${s.school} · ${s.class}</td><td>${tg}</td><td>${ab}</td><td><span class="badge b-green">已开通</span></td><td><div style="display:flex;gap:5px" onclick="event.stopPropagation()"><button class="btn btn-secondary btn-sm" onclick="StudentModule.openDetail('${s.id}')">查看详情</button><button class="btn btn-ghost btn-sm" onclick="Toast.show('编辑 ${dn} 的档案')">编辑</button></div></td></tr>`;
        }).join('') || '<tr><td colspan="7"><div class="empty"><div class="empty-icon">🔍</div><div class="empty-title">无匹配学生</div><div class="empty-desc">尝试调整搜索词或筛选条件</div></div></td></tr>';
        const pi = document.getElementById('student-page-info');
        if (pi) {pi.textContent = `显示 1–${list.length} / 共 ${list.length} 条`;}
    }

    function filterStudents() { renderList(); }

    function setGrade(el, grade) {
        _gradeFilter = grade;
        document.querySelectorAll('#grade-filters .fpill').forEach(p => p.classList.remove('on'));
        if (el) {el.classList.add('on');}
        renderList();
    }

    function toggleAllergyFilter() {
        _allergyOnly = !_allergyOnly;
        const fp = document.getElementById('fpill-allergy');
        if (fp) {fp.classList.toggle('on', _allergyOnly);}
        renderList();
    }

    function toggleFpill(el) { if (el) {el.classList.toggle('on');} }

    // ══════════════════════════════════════════════════════
    //  学生详情
    // ══════════════════════════════════════════════════════
    function openDetail(studentId) {
        const students = Store.getStudents ? Store.getStudents() : [];
        const s = students.find(x => x.id === studentId);
        if (!s) {return;}
        if (Store.setCurrentStudent) {Store.setCurrentStudent(studentId);}
        const nd = document.getElementById('nav-detail');
        const ndn = document.getElementById('nav-detail-name');
        if (nd) {nd.style.display = 'flex';}
        if (ndn) {ndn.textContent = getDisplayName(s);}
        renderDetail(s);
        if (typeof Router !== 'undefined' && Router.navigate) {Router.navigate('student-detail', { studentId });}
        else if (typeof window.nav === 'function') {window.nav('student-detail');}
    }

    function renderDetail(s) {
        if (!s) {
            const students = Store.getStudents ? Store.getStudents() : [];
            const cid = Store.getCurrentStudent ? Store.getCurrentStudent() : null;
            s = students.find(x => x.id === cid);
        }
        if (!s) {return;}
        const content = document.getElementById('student-detail-content');
        if (!content) {return;}
        const at = s.allergy && s.allergy.length > 0 ? s.allergy.map(a => `<span class="atag atag-red">${a}</span>`).join('') : '<span class="atag atag-safe">无过敏记录</span>';
        const dn = getDisplayName(s);
        content.innerHTML = `<div class="student-header"><div class="sh-avatar" style="background:${s.color}">${s.avatar}</div><div><div class="sh-name">${dn}</div><div class="sh-meta">${s.sex} · ${s.age}岁 · 学号 ${s.no} · ${s.school} ${s.class}</div><div class="sh-tags">${(s.tags||[]).map(t=>`<div class="sh-tag">${t}</div>`).join('')}${s.special?`<div class="sh-tag" style="background:rgba(255,200,0,0.18);border-color:rgba(255,200,0,0.3)">${s.special}</div>`:''}</div></div><div class="sh-stats"><div class="sh-stat"><div class="sh-stat-val">${(s.allergy&&s.allergy.length)||'0'}</div><div class="sh-stat-label">过敏记录</div></div><div class="sh-stat"><div class="sh-stat-val">${(s.awards||[]).length}</div><div class="sh-stat-label">获奖记录</div></div><div class="sh-stat"><div class="sh-stat-val">${(s.books||[]).length}</div><div class="sh-stat-label">借阅书目</div></div><div class="sh-stat"><div class="sh-stat-val">${(s.interests||[]).length}</div><div class="sh-stat-label">兴趣标签</div></div></div></div><div class="card" id="detail-card"><div class="tab-bar"><div class="tab active" data-tab="health" onclick="StudentModule.switchTab(this,'health','${s.id}')">🏃 体质健康</div><div class="tab" data-tab="canteen" onclick="StudentModule.switchTab(this,'canteen','${s.id}')">🍱 午餐+晚餐</div><div class="tab" data-tab="awards" onclick="StudentModule.switchTab(this,'awards','${s.id}')">🏆 获奖记录</div><div class="tab" data-tab="activity" onclick="StudentModule.switchTab(this,'activity','${s.id}')">⚽ 课外活动</div><div class="tab" data-tab="reading" onclick="StudentModule.switchTab(this,'reading','${s.id}')">📚 阅读推荐</div><div class="tab" data-tab="resources" onclick="StudentModule.switchTab(this,'resources','${s.id}')">📖 学习资源</div><div class="tab" onclick="StudentModule.switchTab(this,'profile','${s.id}')">👤 基本档案</div></div><div id="tab-content"></div></div>`;
        renderTab('health', s);
    }

    function switchTab(el, tab, sid) {
        document.querySelectorAll('#detail-card .tab').forEach(t => t.classList.remove('active'));
        if (el) {el.classList.add('active');}
        const students = Store.getStudents ? Store.getStudents() : [];
        const s = students.find(x => x.id === sid);
        if (s) {renderTab(tab, s);}
    }

    function renderTab(tab, s) {
        const tc = document.getElementById('tab-content');
        if (!tc) {return;}
        _currentTab = tab;
        switch (tab) {
            case 'health': tc.innerHTML = buildHealthTab(s); break;
            case 'canteen': tc.innerHTML = buildCanteenTab(s); break;
            case 'activity': tc.innerHTML = buildActivityTab(s); break;
            case 'reading': tc.innerHTML = buildReadingTab(s); break;
            case 'profile': tc.innerHTML = buildProfileTab(s); break;
            case 'awards': tc.innerHTML = buildAwardsTab(s); break;
            default: tc.innerHTML = '<div style="padding:18px">功能开发中</div>';
        }
    }

    // ══════════════════════════════════════════════════════
    //  标签页构建函数
    // ══════════════════════════════════════════════════════

    function buildHealthTab(s) {
        const fi = (s.fitness && s.fitness.items) || [];
        const fitHTML = fi.map(i => `<div class="fit-item"><div class="fit-emoji">${i.e}</div><div class="fit-name">${i.n}</div><div class="fit-status ${STATUS_CSS[i.s]}">${STATUS_MAP[i.s]}</div></div>`).join('');
        const ag = _aiGenerated[`health-${s.id}`];
        const blocks = AI_CONTENT.fitness[s.id] || generateDynamicAI('health', s) || [];
        return `<div style="display:grid;grid-template-columns:360px 1fr;gap:16px;padding:18px"><div><div class="card mb14"><div class="card-header"><div class="card-title">本学期体测项目</div><span class="badge b-outline">${ag?'已生成建议':'待生成建议'}</span></div><div class="card-body"><div class="fit-grid">${fitHTML}</div></div></div><div class="card"><div class="card-header"><div class="card-title">健康档案摘要</div></div><div class="card-body" style="padding:12px 16px"><div class="pf"><span class="pf-label">体型状态</span><span class="pf-val">正常体型</span></div><div class="pf"><span class="pf-label">视力</span><span class="pf-val">轻度近视，已配镜</span></div><div class="pf"><span class="pf-label">运动偏好</span><span class="pf-val">${(s.interests||[]).join('、')}</span></div>${s.special?`<div class="pf"><span class="pf-label">特别注意</span><span class="pf-val" style="color:var(--amber)">${s.special}</span></div>`:''}<div class="pf" style="border:none"><span class="pf-label">过敏原</span><div>${s.allergy&&s.allergy.length?s.allergy.map(a=>`<span class="atag atag-red" style="margin:2px">${a}</span>`).join(''):'<span class="atag atag-safe">无记录</span>'}</div></div></div></div></div><div><div class="ai-panel"><div class="ai-panel-header"><div class="ai-icon">🤖</div><div><div class="card-title">AI 体质成长建议</div><div class="card-sub">UniEdu Agent · 基于体测数据与健康档案</div></div><div class="ai-status ${ag?'done':'idle'}" id="ai-status-health"><div class="ai-status-dot"></div><span>${ag?'已生成':'等待生成'}</span></div></div><div class="ai-output ${ag?'visible':''}" id="ai-output-health">${ag?buildAIBlocks(blocks):''}</div>${ag?'':`<button class="ai-gen-btn" id="ai-btn-health" onclick="StudentModule.generateAI('health','${s.id}')"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>生成 AI 健康建议</button>`}<div class="ai-disclaimer">ℹ️ <span>以上为定性引导建议，不构成医疗意见。如有身体异常请及时就医。</span></div></div></div></div>`;
    }

    function buildAIBlocks(blocks) {
        const colorMap = { green: 'var(--green)', amber: 'var(--amber)', teal: 'var(--teal)', purple: 'var(--purple)' };
        return blocks.map(b => '<div class="ai-block"><div class="ai-block-label"><div class="ai-block-dot" style="background:' + (colorMap[b.color] || 'var(--navy-2)') + '"></div><div>' + b.label + '</div></div><div class="ai-text ' + b.color + '">' + b.text + '</div></div>').join('');
    }

    function parseAIResponseText(type, text) {
        try {
            const m = text.match(/\{[\s\S]*\}/);
            if (m) {return JSON.parse(m[0]);}
        } catch (e) { console.error('解析AI响应失败:', e); }
        return null;
    }

    function renderAIResponse(type, aiData, student) {
        if (type === 'health' && aiData) {
            return [
                { label: '整体状况', color: 'green', text: aiData['整体状况'] || '' },
                { label: '重点关注', color: 'amber', text: aiData['重点关注'] || '' },
                { label: '运动建议', color: 'blue', text: aiData['运动建议'] || '' },
                { label: '日常提示', color: 'teal', text: aiData['日常提示'] || '' }
            ];
        }
        return null;
    }

    function generateDynamicAI(type, s) {
        if (type === 'health') {
            const items = (s.fitness && s.fitness.items) || [];
            const good = items.filter(x => x.s === 'good' || x.s === 'great').map(x => x.n);
            const fair = items.filter(x => x.s === 'fair').map(x => x.n);
            const poor = items.filter(x => x.s === 'poor').map(x => x.n);
            const dn = getDisplayName(s);
            const blocks = [];
            blocks.push({ label: '整体状况', color: good.length >= 3 ? 'green' : 'amber',
                text: dn + (good.length >= 3 ? '的体测表现良好，多个项目达到优秀水平。' : '的体测表现中等，建议加强锻炼。') });
            blocks.push({ label: '重点关注', color: poor.length > 0 ? 'amber' : 'green',
                text: poor.length > 0 ? '需要重点关注：' + poor.join('、') + '。' : '各项体能表现良好，继续保持规律运动。' });
            blocks.push({ label: '运动建议', color: 'blue',
                text: (s.interests || []).length > 0 ? '结合' + dn + '的兴趣（' + s.interests.join('、') + '），推荐参与相关活动。' : '建议参与多样化的体育活动。' });
            blocks.push({ label: '日常提示', color: 'teal',
                text: (s.allergy && s.allergy.length > 0) ? '注意过敏原：' + s.allergy.join('、') + '。' : '保持规律作息和均衡饮食。' });
            return blocks;
        } else if (type === 'canteen') {
            return { recommend: 'A', reason: '根据学生体质和偏好推荐。', warn: '', fitness_weak: [], focus: [], dinner: [
                { dish: '清炒时蔬', reason: '富含维生素和膳食纤维', nuts: '纤维3g', icon: '🥬' },
                { dish: '米饭', reason: '提供充足碳水化合物', nuts: '碳水45g', icon: '🍚' },
                { dish: '番茄蛋汤', reason: '补充水分和蛋白质', nuts: '蛋白5g', icon: '🍲' }
            ]};
        } else if (type === 'activity') {
            const map = { '音乐': [{name:'音乐社团',emoji:'🎵',when:'每周三下午',reason:'符合音乐兴趣'}], '绘画': [{name:'美术社团',emoji:'🎨',when:'每周二下午',reason:'符合美术兴趣'}], '阅读': [{name:'阅读俱乐部',emoji:'📚',when:'每周一中午',reason:'符合阅读兴趣'}], '足球': [{name:'足球社团',emoji:'⚽',when:'每周四下午',reason:'符合运动兴趣'}], '篮球': [{name:'篮球社团',emoji:'🏀',when:'每周五下午',reason:'符合运动兴趣'}], '编程': [{name:'编程社团',emoji:'💻',when:'每周三下午',reason:'符合科技兴趣'}] };
            const acts = []; (s.interests || []).forEach(i => { if (map[i]) {acts.push(...map[i]);} });
            if (acts.length === 0) { acts.push({name:'阳光体育',emoji:'🏃',when:'每天课间',reason:'增强体质'},{name:'兴趣社团',emoji:'🎯',when:'每周选修课',reason:'培养爱好'}); }
            return acts.slice(0, 3);
        } else if (type === 'reading') {
            const map = { '音乐': [{t:'音乐简史',a:'走进音乐世界',bg:'#C8720A',spine:'音',reason:'拓展音乐知识'}], '绘画': [{t:'世界名画赏析',a:'艺术入门',bg:'#7C3AED',spine:'画',reason:'培养艺术鉴赏'}], '阅读': [{t:'经典文学名著',a:'教育部推荐',bg:'#2563EB',spine:'读',reason:'提升文学素养'}], '科学': [{t:'少儿科学实验',a:'趣味科学',bg:'#1E5C3A',spine:'科',reason:'培养科学思维'}], '历史': [{t:'中华上下五千年',a:'历史入门',bg:'#DC2626',spine:'历',reason:'了解历史文化'}] };
            const books = []; (s.interests || []).forEach(i => { if (map[i]) {books.push(...map[i]);} });
            if (books.length === 0) { books.push({t:'十万个为什么',a:'科普读物',bg:'#0D7377',spine:'?',reason:'解答好奇'},{t:'成语故事',a:'传统故事',bg:'#C8720A',spine:'成',reason:'学习传统文化'}); }
            return books.slice(0, 3);
        }
        return null;
    }

    function buildCanteenTab(s) {
        const c = AI_CONTENT.canteen[s.id] || {recommend:'B',reason:'',warn:''};
        const sn = STUDENT_NUTR[s.id];
        const alreadyGen = _aiGenerated['canteen-'+s.id];
        const mA = MEAL_NUTRITION.A, mB = MEAL_NUTRITION.B;
        const recMeal = sn ? sn.rec : c.recommend;

        function nbar(labelA, valA, valB, labelB, unit, color) {
            const maxV = Math.max(valA,valB)*1.2||1;
            const pA=Math.round(valA/maxV*100), pB=Math.round(valB/maxV*100);
            const wA=valA>=valB?'font-weight:700;color:var(--green)':'color:var(--ink-3)';
            const wB=valB>=valA?'font-weight:700;color:var(--green)':'color:var(--ink-3)';
            return '<div style="display:flex;align-items:center;gap:6px;padding:5px 0;border-bottom:1px solid #F3F0EA">'
                +'<div style="width:80px;font-size:11px;color:var(--ink-4)">'+labelA+'</div>'
                +'<div style="'+wA+';font-size:11px;width:36px;text-align:right;flex-shrink:0">'+valA+unit+'</div>'
                +'<div style="flex:1;height:4px;background:#EEE;border-radius:2px;overflow:hidden">'
                +'<div style="width:'+pA+'%;height:100%;background:'+(valA>=valB?color:'#D1C4B0')+';border-radius:2px"></div></div>'
                +'<div style="flex:1;height:4px;background:#EEE;border-radius:2px;overflow:hidden">'
                +'<div style="width:'+pB+'%;height:100%;background:'+(valB>=valA?color:'#D1C4B0')+';border-radius:2px"></div></div>'
                +'<div style="'+wB+';font-size:11px;width:36px;flex-shrink:0">'+valB+unit+'</div>'
                +'</div>';
        }

        const lunchReason = sn ? sn.lunch_reason : (c.reason || '两餐均无明显冲突，可自由选择。');
        const dinnerHTML = buildDinnerHTML(sn);
        const fitWeakTags = sn ? sn.fitness_weak.map(w=>'<span class="badge b-amber" style="margin:2px">'+w+'</span>').join('') : '';
        const focusTags = sn ? sn.focus.map(f=>{
            const nm={protein:'优质蛋白',iron:'铁质',calcium:'钙质',zinc:'锌',vitC:'维生素C',vitB:'B族维生素',vitD:'维生素D',carbs:'复合碳水',fiber:'膳食纤维'}[f]||f;
            return '<span class="badge b-blue">'+nm+'</span>';
        }).join('') : '';

        return '<div style="padding:18px">'
            +'<div class="meal-grid">'
            +'<div class="meal-card '+(recMeal==='A'?'rec':'')+'">'+(recMeal==='A'?'<div class="meal-rec-label">✓ AI 推荐午餐</div>':'')
            +'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'
            +'<div><div class="meal-type">A 餐</div><div class="meal-title">'+mA.name+'</div></div>'
            +'<div style="text-align:right"><div style="font-size:18px;font-weight:700;color:'+(recMeal==='A'?'var(--green)':'var(--ink-4)')+'">'+mA.cal+'</div><div style="font-size:10px;color:var(--ink-4)">kcal</div></div></div>'
            +'<ul class="meal-items" style="margin-bottom:10px">'+mA.items.map(i=>'<li class="'+(s.allergy&&s.allergy.some(a=>i.tags.includes(a))?'warn':'')+'">'
                +i.n+(s.allergy&&s.allergy.some(a=>i.tags.includes(a))?' ⚠':'')+'<span style="margin-left:auto;font-size:10px;color:var(--ink-4)">'+i.note+'</span></li>').join('')+'</ul>'
            +(c.warn?'<div class="meal-note warn">⚠ '+c.warn+'</div>':'<div class="meal-note ok">✓ 无过敏冲突</div>')
            +'</div>'
            +'<div class="meal-card '+(recMeal==='B'?'rec':'')+'">'+(recMeal==='B'?'<div class="meal-rec-label">✓ AI 推荐午餐</div>':'')
            +'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'
            +'<div><div class="meal-type">B 餐</div><div class="meal-title">'+mB.name+'</div></div>'
            +'<div style="text-align:right"><div style="font-size:18px;font-weight:700;color:'+(recMeal==='B'?'var(--green)':'var(--ink-4)')+'">'+mB.cal+'</div><div style="font-size:10px;color:var(--ink-4)">kcal</div></div></div>'
            +'<ul class="meal-items" style="margin-bottom:10px">'+mB.items.map(i=>'<li class="'+(s.allergy&&s.allergy.some(a=>i.tags.includes(a))?'warn':'')+'">'
                +i.n+(s.allergy&&s.allergy.some(a=>i.tags.includes(a))?' ⚠':'')+'<span style="margin-left:auto;font-size:10px;color:var(--ink-4)">'+i.note+'</span></li>').join('')+'</ul>'
            +'<div class="meal-note ok">✓ 与过敏档案无冲突</div>'
            +'</div></div>'
            +'<div class="g2 mb14">'
            +'<div class="card"><div class="card-header"><div><div class="card-title">营养素对比</div><div class="card-sub">A 餐 vs B 餐</div></div>'
            +'<div style="font-size:10px;color:var(--ink-4);display:flex;gap:10px"><span>A餐&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;B餐</span></div></div>'
            +'<div class="card-body" style="padding:6px 16px 10px">'
            +nbar('蛋白质',mA.protein,mB.protein,'','g','#3B82F6')
            +nbar('热 量',mA.cal,mB.cal,'','kcal','#F59E0B')
            +nbar('脂 肪',mA.fat,mB.fat,'','g','#EF4444')
            +nbar('铁 质',mA.iron,mB.iron,'','mg','#DC2626')
            +nbar('钙 质',mA.calcium,mB.calcium,'','mg','#0D9488')
            +nbar('膳食纤维',mA.fiber,mB.fiber,'','g','#16A34A')
            +'<div style="font-size:10px;color:var(--ink-4);text-align:center;padding-top:8px">绿色 = 该餐此项更高</div>'
            +'</div></div>'
            +'<div class="card"><div class="card-header"><div class="card-title">📊 体质-营养关联</div><div class="card-sub">基于 '+getDisplayName(s)+' 的体测结果</div></div>'
            +'<div class="card-body" style="padding:12px 16px">'
            +(sn?'<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:600;color:var(--ink-4);margin-bottom:5px">体测待提升项目</div><div>'+fitWeakTags+'</div></div>'
                +'<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:600;color:var(--ink-4);margin-bottom:5px">重点营养需求</div><div>'+focusTags+'</div></div>'
                +'<div class="callout amber" style="margin:0"><span>💡</span><span style="font-size:12px">'+sn.nutr_tip+'</span></div>'
                :'<div class="empty"><div class="empty-title">暂无数据</div></div>')
            +'</div></div></div>'
            +'<div class="ai-panel">'
            +'<div class="ai-panel-header"><div class="ai-icon" style="background:var(--amber)">🤖</div>'
            +'<div><div class="card-title">AI 全天营养规划</div><div class="card-sub">午餐选餐 · 晚餐方案 · 体质驱动</div></div>'
            +'<div class="ai-status '+(alreadyGen?'done':'idle')+'" id="ai-status-canteen"><div class="ai-status-dot"></div><span>'+(alreadyGen?'已生成':'等待生成')+'</span></div>'
            +'</div>'
            +(!alreadyGen?'<button class="ai-gen-btn" style="background:var(--amber)" id="ai-btn-canteen" onclick="StudentModule.generateAI(&quot;canteen&quot;,&quot;'+s.id+'&quot;)">✦ 生成 AI 午餐 + 晚餐营养方案</button>':'')
            +'<div class="ai-output '+(alreadyGen?'visible':'')+'" id="ai-output-canteen">'+(alreadyGen?buildCanteenOutput(lunchReason,recMeal,dinnerHTML,sn):'')+'</div>'
            +'<div class="ai-disclaimer">ℹ️ <span>营养建议仅供参考，严重过敏或有医嘱请优先遵从医生指导。</span></div>'
            +'</div></div>';
    }

    function buildDinnerHTML(sn) {
        if (!sn) {return '';}
        return sn.dinner.map(d=>
            '<div style="display:flex;gap:10px;padding:10px 0;border-bottom:1px solid #F3F0EA">'
            +'<div style="font-size:20px;flex-shrink:0;padding-top:2px">'+d.icon+'</div>'
            +'<div style="flex:1">'
            +'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">'
            +'<span style="font-size:13px;font-weight:600;color:var(--ink)">'+d.dish+'</span>'
            +'<span style="font-size:10px;background:var(--green-l);color:#15803D;padding:2px 7px;border-radius:10px;font-weight:600">'+d.nuts+'</span>'
            +'</div>'
            +'<div style="font-size:12px;line-height:1.6;color:var(--ink-2)">'+d.reason+'</div>'
            +'</div></div>'
        ).join('');
    }

    function buildCanteenOutput(lunchReason, recMeal, dinnerHTML, sn, warn) {
        const fitnessWeak = sn && sn.fitness_weak ? sn.fitness_weak : [];
        const focus = sn && sn.focus ? sn.focus : [];
        return '<div style="padding:14px 18px;border-bottom:1px solid var(--border)">'
            +'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
            +'<div style="width:5px;height:20px;background:var(--amber);border-radius:3px"></div>'
            +'<div style="font-size:12px;font-weight:700;color:var(--ink-3);letter-spacing:.05em">今日午餐推荐</div>'
            +'<span class="badge b-amber" style="margin-left:auto">推荐选 '+recMeal+' 餐</span></div>'
            +'<div class="ai-text amber" style="margin:0">'+lunchReason+'</div></div>'
            +'<div style="padding:14px 18px">'
            +'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
            +'<div style="width:5px;height:20px;background:var(--teal);border-radius:3px"></div>'
            +'<div style="font-size:12px;font-weight:700;color:var(--ink-3);letter-spacing:.05em">今晚家庭晚餐方案</div>'
            +'<span class="badge b-teal" style="margin-left:auto">补足午餐 · 强化体质</span></div>'
            +(fitnessWeak.length > 0 ? '<div style="font-size:12px;color:var(--ink-4);margin-bottom:8px">针对「'+fitnessWeak.join('·')+'」待提升，重点补充 '
                +focus.map(f=>({protein:'蛋白质',iron:'铁质',calcium:'钙质',zinc:'锌',vitC:'维C',vitB:'B族',vitD:'维D',carbs:'复合碳水',fiber:'纤维'}[f]||f)).join('、')+'</div>' : '')
            +dinnerHTML
            +(warn ? '<div style="margin-top:12px;padding:10px 12px;background:#FEF2F2;border-radius:6px;font-size:12px;color:#DC2626;line-height:1.65">⚠️ <strong>过敏提醒：</strong>'+warn+'</div>' : '')
            +'<div style="margin-top:12px;padding:10px 12px;background:var(--paper);border-radius:6px;font-size:12px;color:var(--ink-4);line-height:1.65">'
            +'💡 <strong>烹饪提示：</strong>蒸煮炖优先，少油少盐，晚餐热量约全天30%。</div>'
            +'</div>';
    }

    async function generateAI(type, sid) {
        const btn = document.getElementById('ai-btn-' + type);
        const statusEl = document.getElementById('ai-status-' + type);
        if (!btn) {return;}
        const students = Store.getStudents ? Store.getStudents() : [];
        const s = students.find(x => x.id === sid);
        if (!s) {return;}
        btn.disabled = true;
        btn.innerHTML = '<div class="spinner"></div> AI 分析中...';
        if (statusEl) { statusEl.className = 'ai-status loading'; statusEl.innerHTML = '<div class="ai-status-dot"></div><span>生成中</span>'; }
        if (!AI_CONFIG.useMockData) {
            try {
                const aiResponse = typeof callAI === 'function' ? await callAI(type, s) : null;
                if (aiResponse) { const aiData = parseAIResponseText(type, aiResponse); console.log('AI响应数据:', aiData); }
            } catch (error) { console.error('AI调用失败:', error); }
        }
        setTimeout(() => {
            _aiGenerated[type + '-' + sid] = true;
            const outputEl = document.getElementById('ai-output-' + type);
            if (type === 'health' && outputEl) {
                const blocks = AI_CONTENT.fitness[sid] || generateDynamicAI('health', s);
                outputEl.innerHTML = buildAIBlocks(blocks);
                outputEl.classList.add('visible');
                if (statusEl) { statusEl.className = 'ai-status done'; statusEl.innerHTML = '<div class="ai-status-dot"></div><span>已生成</span>'; }
                btn.remove(); typewriterEffect(outputEl);
            } else if (type === 'canteen' && outputEl) {
                const sn = STUDENT_NUTR[sid]; const dc = AI_CONTENT.canteen[sid] || {recommend:'B',reason:'',warn:''};
                const dyn = generateDynamicAI('canteen', s);
                const rm = sn ? sn.rec : (dyn ? dyn.recommend : dc.recommend);
                const lr = sn ? sn.lunch_reason : (dyn ? dyn.reason : dc.reason);
                const dh = sn ? buildDinnerHTML(sn) : buildDinnerHTML(dyn || dc);
                outputEl.innerHTML = buildCanteenOutput(lr, rm, dh, sn || dyn);
                outputEl.classList.add('visible');
                if (statusEl) { statusEl.className = 'ai-status done'; statusEl.innerHTML = '<div class="ai-status-dot"></div><span>已生成</span>'; }
                btn.remove(); typewriterEffect(outputEl);
            } else if (type === 'activity') {
                const acts = AI_CONTENT.activity[sid] || generateDynamicAI('activity', s) || [];
                const emptyEl = document.getElementById('activity-empty-' + sid);
                const cardsEl = document.getElementById('activity-cards-' + sid);
                if (emptyEl) {emptyEl.style.display = 'none';}
                if (cardsEl) {
                    cardsEl.innerHTML = acts.map((a,i) => '<div class="act-card" style="opacity:0;animation:fadeUp 0.4s ease '+(i*0.15)+'s forwards"><div class="act-emoji">'+a.emoji+'</div><div class="act-name">'+a.name+'</div><div class="act-when">'+a.when+'</div><div class="act-reason">'+a.reason+'</div><button class="act-register-btn" onclick="StudentModule.registerActivity(this,\''+sid+'\','+i+',\''+a.name+'\')">感兴趣，了解更多</button></div>').join('');
                    cardsEl.style.display = 'grid';
                }
                if (statusEl) { statusEl.className = 'ai-status done'; statusEl.innerHTML = '<div class="ai-status-dot"></div><span>已生成</span>'; }
                btn.remove();
            } else if (type === 'reading') {
                const books = AI_CONTENT.reading[sid] || generateDynamicAI('reading', s) || [];
                const emptyEl = document.getElementById('books-empty-' + sid);
                const outEl = document.getElementById('books-output-' + sid);
                if (emptyEl) {emptyEl.style.display = 'none';}
                if (outEl) {
                    outEl.innerHTML = books.map((b,i) => '<div class="book-card" style="margin-bottom:12px;opacity:0;animation:fadeUp 0.4s ease '+(i*0.2)+'s forwards"><div class="book-spine" style="background:'+b.bg+'">'+b.spine+'</div><div style="flex:1"><div class="book-title">'+b.t+'</div><div class="book-author">'+b.a+'</div><div class="book-reason">'+b.reason+'</div><div style="display:flex;gap:6px;align-items:center"><button class="book-add-btn" onclick="StudentModule.addBook(this,\''+sid+'\','+i+',\''+b.t+'\')">+ 加入书单</button><span class="badge b-green" style="font-size:10px">馆内有货</span></div></div></div>').join('');
                    outEl.style.display = 'block';
                }
                if (statusEl) { statusEl.className = 'ai-status done'; statusEl.innerHTML = '<div class="ai-status-dot"></div><span>已生成</span>'; }
                btn.remove();
            }
            if (typeof Toast !== 'undefined') {Toast.show('✓ ' + getDisplayName(s) + ' 的 AI 建议已生成');}
        }, 2200);
    }

    function typewriterEffect(container) {
        container.querySelectorAll('.ai-text').forEach((el, i) => {
            el.style.opacity = '0';
            el.style.transition = 'opacity 0.5s ease ' + (i * 0.3) + 's';
            setTimeout(() => { el.style.opacity = '1'; }, 50 + i * 300);
        });
    }

    function buildActivityTab(s) {
        const acts = AI_CONTENT.activity[s.id] || [];
        const alreadyGen = _aiGenerated['activity-'+s.id];
        const actCards = acts.map((a, i) => `<div class="act-card"><div class="act-emoji">${a.emoji}</div><div class="act-name">${a.name}</div><div class="act-when">${a.when}</div><div class="act-reason">${a.reason}</div><button class="act-register-btn ${_aiGenerated['act-reg-'+s.id+'-'+i]?'done':''}" id="act-btn-${s.id}-${i}" onclick="StudentModule.registerActivity(this,'${s.id}',${i},'${a.name}')">${_aiGenerated['act-reg-'+s.id+'-'+i]?'✓ 已标记感兴趣':'感兴趣，了解更多'}</button></div>`).join('');
        return `<div style="padding:18px"><div style="display:grid;grid-template-columns:340px 1fr;gap:16px"><div><div class="card mb14"><div class="card-header"><div class="card-title">学生兴趣与体能</div></div><div class="card-body" style="padding:12px 16px"><div class="pf"><span class="pf-label">填报兴趣</span><span class="pf-val">${(s.interests||[]).join('、')}</span></div><div class="pf"><span class="pf-label">体能优势</span><span class="pf-val">${((s.fitness && s.fitness.items)||[]).filter(x=>x.s==='good'||x.s==='great').map(x=>x.n).join('、')||'待完善'}</span></div><div class="pf"><span class="pf-label">体能注意</span><span class="pf-val" style="color:${s.special?'var(--amber)':'var(--ink)'}">${s.special||'无'}</span></div><div class="pf" style="border:none"><span class="pf-label">家长授权</span><span class="pf-val" style="color:var(--green)">✓ 可参加校内活动</span></div></div></div><div class="card"><div class="card-header"><div class="card-title">AI 匹配流程</div></div><div class="card-body" style="padding:12px 16px"><div class="step"><div class="step-num" style="background:var(--teal)">1</div><div class="step-body"><div class="step-title">读取兴趣偏好</div><div class="step-desc">学生/家长主动填报的标签</div></div></div><div class="step"><div class="step-num" style="background:var(--teal)">2</div><div class="step-body"><div class="step-title">比对体能状况</div><div class="step-desc">结合体测结果，排除不适合项目</div></div></div><div class="step" style="padding-bottom:0"><div class="step-num" style="background:var(--teal)">3</div><div class="step-body" style="padding-bottom:0"><div class="step-title">从社团库中推荐</div><div class="step-desc">给出 2–3 个匹配度高的活动选项</div></div></div></div></div></div><div><div class="ai-panel mb14"><div class="ai-panel-header"><div class="ai-icon" style="background:var(--teal)">🤖</div><div><div class="card-title">AI 课外活动推荐</div><div class="card-sub">综合兴趣 · 体能 · 时间匹配</div></div><div class="ai-status ${alreadyGen?'done':'idle'}" id="ai-status-activity"><div class="ai-status-dot"></div><span>${alreadyGen?'已生成':'等待生成'}</span></div></div>${alreadyGen ? '' : `<button class="ai-gen-btn" style="background:var(--teal)" id="ai-btn-activity" onclick="StudentModule.generateAI('activity','${s.id}')"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>生成活动推荐</button>`}</div><div id="activity-cards-${s.id}" class="g3" style="${alreadyGen?'':'display:none'}">${actCards}</div>${alreadyGen ? '' : `<div class="empty" id="activity-empty-${s.id}"><div class="empty-icon">⚽</div><div class="empty-title">点击上方按钮生成推荐</div><div class="empty-desc">AI 将基于 ${getDisplayName(s)} 的信息匹配合适活动</div></div>`}</div></div></div>`;
    }

    function buildReadingTab(s) {
        const books = AI_CONTENT.reading[s.id] || [];
        const alreadyGen = _aiGenerated['reading-'+s.id];
        const booksHTML = books.map((b, i) => `<div class="book-card" style="margin-bottom:12px"><div class="book-spine" style="background:${b.bg}">${b.spine}</div><div style="flex:1"><div class="book-title">${b.t}</div><div class="book-author">${b.a}</div><div class="book-reason">${b.reason}</div><div style="display:flex;gap:6px;align-items:center"><button class="book-add-btn ${_aiGenerated['book-'+s.id+'-'+i]?'added':''}" onclick="StudentModule.addBook(this,'${s.id}',${i},'${b.t}')">${_aiGenerated['book-'+s.id+'-'+i]?'✓ 已加入书单':'+ 加入书单'}</button><span class="badge b-green" style="font-size:10px">馆内有货</span></div></div></div>`).join('');
        const histHTML = (s.books||[]).map(b => `<div style="display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid #F3F0EA;font-size:13px"><span style="color:var(--ink)">${b.t}</span><div style="display:flex;align-items:center;gap:6px"><span style="font-size:11px;color:var(--ink-4)">${b.a}</span><span class="badge ${b.s==='已完成'?'b-green':'b-amber'}">${b.s}</span></div></div>`).join('');
        return `<div style="display:grid;grid-template-columns:340px 1fr;gap:16px;padding:18px"><div><div class="card mb14"><div class="card-header"><div class="card-title">图书馆借阅记录</div></div><div class="card-body" style="padding:4px 16px">${histHTML||'<div class="empty" style="padding:24px"><div class="empty-title">暂无借阅记录</div></div>'}</div></div><div class="card"><div class="card-header"><div class="card-title">AI 提取阅读标签</div></div><div class="card-body"><div style="display:flex;flex-wrap:wrap;gap:6px">${(s.interests||[]).map(i=>`<span class="badge b-purple">${i}</span>`).join('')}<span class="badge b-blue">长篇耐读</span><span class="badge b-green">兴趣驱动</span></div><div class="callout blue" style="margin-top:12px"><span>🔒</span><span>仅使用借阅记录，不关联课内作业，阅读推荐完全基于兴趣。</span></div></div></div></div><div><div class="ai-panel mb14"><div class="ai-panel-header"><div class="ai-icon" style="background:var(--purple)">🤖</div><div><div class="card-title">AI 个性化书单推荐</div><div class="card-sub">基于借阅偏好 · 馆藏匹配</div></div><div class="ai-status ${alreadyGen?'done':'idle'}" id="ai-status-reading"><div class="ai-status-dot"></div><span>${alreadyGen?'已生成':'等待生成'}</span></div></div>${alreadyGen ? '' : `<button class="ai-gen-btn" style="background:var(--purple)" id="ai-btn-reading" onclick="StudentModule.generateAI('reading','${s.id}')"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>生成专属书单</button>`}</div><div id="books-output-${s.id}" style="${alreadyGen?'':'display:none'}">${booksHTML}</div>${alreadyGen ? '' : `<div class="empty" id="books-empty-${s.id}"><div class="empty-icon">📚</div><div class="empty-title">点击上方按钮生成书单</div><div class="empty-desc">AI 将基于 ${getDisplayName(s)} 的借阅历史推荐合适书目</div></div>`}</div></div></div>`;
    }

    function buildProfileTab(s) {
        return `<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:18px"><div class="card"><div class="card-header"><div class="card-title">基本信息</div><div style="display:flex;gap:8px"><button class="btn btn-primary btn-sm" onclick="StudentModule.openEditStudent('${s.id}')">编辑</button><button class="btn btn-danger btn-sm" onclick="StudentModule.confirmDeleteStudent('${s.id}')">删除</button></div></div><div class="card-body" style="padding:12px 16px"><div class="pf"><span class="pf-label">姓名</span><span class="pf-val">${getDisplayName(s)}</span></div><div class="pf"><span class="pf-label">性别</span><span class="pf-val">${s.sex}</span></div><div class="pf"><span class="pf-label">年龄</span><span class="pf-val">${s.age} 岁</span></div><div class="pf"><span class="pf-label">学号</span><span class="pf-val mono">${s.no}</span></div><div class="pf"><span class="pf-label">学校</span><span class="pf-val">${s.school}</span></div><div class="pf" style="border:none"><span class="pf-label">班级</span><span class="pf-val">${s.class}</span></div></div></div><div class="card"><div class="card-header"><div class="card-title">健康与过敏信息</div><button class="btn btn-secondary btn-sm" onclick="Toast.show('家长端可更新此信息')">家长更新</button></div><div class="card-body" style="padding:12px 16px"><div class="pf"><span class="pf-label">过敏原</span><div>${s.allergy&&s.allergy.length?s.allergy.map(a=>`<span class="atag atag-red" style="margin:2px">${a}</span>`).join(''):'<span class="atag atag-safe">无记录</span>'}</div></div><div class="pf"><span class="pf-label">饮食备注</span><span class="pf-val">${s.diet_note||'无'}</span></div><div class="pf" style="border:none"><span class="pf-label">特别注意</span><span class="pf-val" style="color:${s.special?'var(--amber)':'var(--ink)'}">${s.special||'无'}</span></div></div></div><div class="card"><div class="card-header"><div class="card-title">兴趣标签</div><button class="btn btn-secondary btn-sm" onclick="Toast.show('学生可自助更新兴趣标签')">学生更新</button></div><div class="card-body"><div style="display:flex;flex-wrap:wrap;gap:6px">${(s.interests||[]).map(i=>`<span class="badge b-teal">${i}</span>`).join('')}</div></div></div><div class="card"><div class="card-header"><div class="card-title">AI 服务授权</div></div><div class="card-body" style="padding:12px 16px"><div class="pf"><span class="pf-label">体质健康建议</span><span class="badge b-green">已授权</span></div><div class="pf"><span class="pf-label">推餐服务</span><span class="badge b-green">已授权</span></div><div class="pf"><span class="pf-label">活动推荐</span><span class="badge b-green">已授权</span></div><div class="pf" style="border:none"><span class="pf-label">阅读推荐</span><span class="badge b-green">已授权</span></div></div></div></div>`;
    }

    function buildAwardsTab(s) {
        const aws = [...(s.awards || [])];
        const clubs = (typeof Store !== 'undefined' && Store.get('clubs_by_student')) ? (Store.get('clubs_by_student')[s.name] || []) : [];
        if (aws.length === 0 && clubs.length === 0) {
            return '<div style="padding:18px"><div class="card"><div class="card-body"><div class="empty"><div class="empty-icon">🏆</div><div class="empty-title">暂无获奖记录</div><div class="empty-desc">该生本学期暂未录入获奖信息<br><span style="font-size:11px;color:var(--ink-4)">数据来源：2025学年第一学期综合学科条线赛事</span></div></div></div></div></div>';
        }
        const lvlCount = {};
        const subjCount = {};
        aws.forEach(a => {
            lvlCount[a.level] = (lvlCount[a.level]||0)+1;
            subjCount[a.subject] = (subjCount[a.subject]||0)+1;
        });
        const lvlColor = {'国家级':'#DC2626','市级':'#7C3AED','区级':'#C8720A','校级':'#0D7377'};
        const lvlBg = {'国家级':'#FEE2E2','市级':'#EDE9FE','区级':'#FEF3C7','校级':'#CCFBF1'};
        const prizeColor = {'一等奖':'#DC2626','二等奖':'#EA580C','三等奖':'#C8720A','金奖':'#DC2626','银奖':'#6B7280','铜奖':'#92400E','第一名':'#DC2626','第二名':'#EA580C','第三名':'#C8720A'};
        const kpiHTML = ['国家级','市级','区级','校级'].filter(l=>lvlCount[l]).map(l =>
            `<div class="kpi" style="border-color:${lvlColor[l]};background:${lvlBg[l]}"><div class="kpi-label">${l}获奖</div><div class="kpi-val" style="color:${lvlColor[l]}">${lvlCount[l]}</div><div class="kpi-sub">项</div></div>`
        ).join('');
        const subjHTML = Object.keys(subjCount).map(sb =>
            `<span class="badge b-blue" style="margin:3px;font-size:11px">${sb} · ${subjCount[sb]}</span>`
        ).join('');
        const lvlOrder = {'国家级':0,'市级':1,'区级':2,'校级':3};
        const sorted = [...aws].sort((a,b) => ((lvlOrder[a.level] !== undefined ? lvlOrder[a.level] : 9)) - ((lvlOrder[b.level] !== undefined ? lvlOrder[b.level] : 9)));
        const rowsHTML = sorted.map(a => {
            const pColor = prizeColor[a.prize] || 'var(--ink-3)';
            return `<tr><td><span class="badge" style="background:${lvlBg[a.level]||'#F3F4F6'};color:${lvlColor[a.level]||'var(--ink-3)'};border:1px solid ${lvlColor[a.level]||'var(--border)'};font-weight:600">${a.level}</span></td><td class="bold" style="max-width:340px">${a.name}</td><td><span style="color:${pColor};font-weight:700">${a.prize}</span></td><td><span class="badge b-outline">${a.subject}</span></td><td class="mono" style="font-size:11px;color:var(--ink-4)">${a.date}</td><td style="font-size:11px;color:var(--ink-4)">${a.org||'—'}</td></tr>`;
        }).join('');
        const top = sorted[0];
        const topPColor = prizeColor[(top && top.prize)] || 'var(--ink-3)';
        return '<div style="padding:18px">'
            + (top?`<div class="g2 mb14" style="grid-template-columns:1.2fr 1fr"><div class="card" style="background:linear-gradient(135deg,#FFF7ED 0%,#FEF3C7 100%);border-color:#F59E0B"><div class="card-header" style="border-bottom:1px solid rgba(245,158,11,0.25)"><div><div class="card-title">🌟 最高荣誉</div><div class="card-sub">本学期最具代表性获奖</div></div><span class="badge" style="background:${lvlBg[top.level]};color:${lvlColor[top.level]};border:1px solid ${lvlColor[top.level]};font-weight:700">${top.level}</span></div><div class="card-body"><div style="font-size:16px;font-weight:700;color:var(--ink);margin-bottom:8px;line-height:1.4">${top.name}</div><div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap"><div><span style="font-size:11px;color:var(--ink-4)">获奖等第</span><div style="font-size:20px;font-weight:800;color:${topPColor}">${top.prize}</div></div><div style="width:1px;height:32px;background:rgba(0,0,0,0.08)"></div><div><span style="font-size:11px;color:var(--ink-4)">学科</span><div style="font-size:13px;font-weight:600;color:var(--ink)">${top.subject}</div></div><div style="width:1px;height:32px;background:rgba(0,0,0,0.08)"></div><div><span style="font-size:11px;color:var(--ink-4)">获奖时间</span><div style="font-size:13px;font-weight:600;color:var(--ink)" class="mono">${top.date}</div></div></div></div></div><div class="card"><div class="card-header"><div class="card-title">🎯 获奖学科分布</div><div class="card-sub">${aws.length} 项 · ${Object.keys(subjCount).length} 个学科</div></div><div class="card-body">${subjHTML}</div></div></div>`:'')
            + (kpiHTML?`<div style="display:grid;grid-template-columns:repeat(${Math.max(2,Object.keys(lvlCount).length)},1fr);gap:12px;margin-bottom:14px">${kpiHTML}</div>`:'')
            + (rowsHTML?`<div class="card"><div class="card-header"><div><div class="card-title">📋 获奖明细</div><div class="card-sub">数据来源：校级竞赛获奖名单 · 学生获奖情况 · 综合学科条线赛事</div></div><button class="btn btn-secondary btn-sm" onclick="Toast.show('正在导出 ${getDisplayName(s)} 的获奖证明...')">↓ 导出证明</button></div><table class="tbl"><thead><tr><th>级别</th><th>赛事名称</th><th>等第</th><th>学科</th><th>时间</th><th>颁奖单位</th></tr></thead><tbody>${rowsHTML}</tbody></table></div>`:'')
            + (clubs.length ? `<div class="card" style="margin-top:14px"><div class="card-header"><div class="card-title">⚽ 社团/拓展课参与记录</div><div class="card-sub">数据来源：学生参加社团</div></div><table class="tbl"><thead><tr><th>社团名称</th><th>指导老师</th><th>上课地点</th><th>学年</th></tr></thead><tbody>${clubs.map(c => `<tr><td class="bold">${c.club_name||'—'}</td><td>${c.teacher||'—'}</td><td style="font-size:12px;color:var(--ink-4)">${c.location||'—'}</td><td><span class="badge b-outline">${c.school_year||'—'}</span></td></tr>`).join('')}</tbody></table></div>` : '')
            + '<div class="callout" style="margin-top:14px;background:var(--blue-light);border:1px solid #BFD3E6"><span>ℹ️</span><span style="font-size:12px">获奖记录与社团数据已同步至学生综合素养成长报告。</span></div></div>';
    }

    function registerActivity(btn, sid, idx, name) {
        _aiGenerated['act-reg-' + sid + '-' + idx] = true;
        btn.textContent = '✓ 已标记感兴趣';
        btn.classList.add('done');
        if (typeof Toast !== 'undefined') {Toast.show('已标记对"' + name + '"感兴趣，教师将收到通知');}
    }

    function addBook(btn, sid, idx, title) {
        _aiGenerated['book-' + sid + '-' + idx] = true;
        btn.textContent = '✓ 已加入书单';
        btn.classList.add('added');
        if (typeof Toast !== 'undefined') {Toast.show('《' + title + '》已加入书单，可前往图书馆借阅');}
    }

    // ══════════════════════════════════════════════════════
    //  CRUD 操作
    // ══════════════════════════════════════════════════════

    function openAddStudent() {
        document.getElementById('overlay-add-student').classList.add('open');
    }

    function closeModal(id) {
        document.getElementById('overlay-' + id).classList.remove('open');
    }

    async function submitAddStudent() {
        const name = document.getElementById('add-name').value.trim();
        const no = document.getElementById('add-id').value.trim();
        const sex = document.getElementById('add-sex').value;
        const school = document.getElementById('add-school').value;
        const className = document.getElementById('add-class').value.trim();
        const grade = document.getElementById('add-grade').value;
        const age = parseInt(document.getElementById('add-age').value) || 10;
        const allergyStr = document.getElementById('add-allergy').value.trim();
        const special = document.getElementById('add-special').value.trim();
        const dietNote = document.getElementById('add-diet-note').value.trim();
        const interestsStr = document.getElementById('add-interests').value.trim();
        if (!name || !no) { if (typeof Toast !== 'undefined') {Toast.show('请填写姓名和学号');} return; }
        const allergy = allergyStr ? allergyStr.split(/[,，]/).map(s => s.trim()).filter(s => s) : [];
        const interests = interestsStr ? interestsStr.split(/[,，]/).map(s => s.trim()).filter(s => s) : ['阅读'];
        try {
            const newStudent = await StudentService.create({ name, no, grade, school: school || '宝山实验学校', class: className || '待分配', age, sex, allergy, diet_note: dietNote, special, interests });
            ['add-name','add-id','add-allergy','add-special','add-diet-note','add-interests','add-class','add-age'].forEach(id => document.getElementById(id).value = '');
            closeModal('add-student');
            renderList();
            if (typeof Toast !== 'undefined') {Toast.show('✓ 学生档案「' + newStudent.displayName + '」已创建');}
        } catch (err) {
            if (typeof Toast !== 'undefined') {Toast.show('✗ 创建失败: ' + err.message);}
        }
    }

    async function openEditStudent(id) {
        _editingStudentId = id;
        const student = await StudentService.getRawById(id);
        if (!student) { if (typeof Toast !== 'undefined') {Toast.show('学生不存在');} return; }
        document.getElementById('edit-name').value = student.name || '';
        document.getElementById('edit-id').value = student.no || '';
        document.getElementById('edit-sex').value = student.sex || '男';
        document.getElementById('edit-age').value = student.age || 10;
        document.getElementById('edit-school').value = student.school || '宝山实验学校';
        document.getElementById('edit-grade').value = student.grade || '小学';
        document.getElementById('edit-class').value = student.class || '';
        document.getElementById('edit-allergy').value = (student.allergy || []).join(',');
        document.getElementById('edit-special').value = student.special || '';
        document.getElementById('edit-diet-note').value = student.diet_note || '';
        document.getElementById('edit-interests').value = (student.interests || []).join(',');
        document.getElementById('overlay-edit-student').classList.add('open');
    }

    async function submitEditStudent() {
        if (!_editingStudentId) {return;}
        const name = document.getElementById('edit-name').value.trim();
        const no = document.getElementById('edit-id').value.trim();
        if (!name || !no) { if (typeof Toast !== 'undefined') {Toast.show('请填写姓名和学号');} return; }
        const changes = {
            name, no, sex: document.getElementById('edit-sex').value,
            school: document.getElementById('edit-school').value,
            grade: document.getElementById('edit-grade').value,
            class: document.getElementById('edit-class').value.trim() || '待分配',
            age: parseInt(document.getElementById('edit-age').value) || 10,
            allergy: (document.getElementById('edit-allergy').value.trim().split(/[,，]/).map(s => s.trim()).filter(s => s)),
            special: document.getElementById('edit-special').value.trim(),
            diet_note: document.getElementById('edit-diet-note').value.trim(),
            interests: (document.getElementById('edit-interests').value.trim().split(/[,，]/).map(s => s.trim()).filter(s => s)) || ['阅读']
        };
        try {
            await StudentService.update(_editingStudentId, changes);
            closeModal('edit-student');
            renderList();
            renderDetail();
            if (typeof Toast !== 'undefined') {Toast.show('✓ 学生档案已更新');}
        } catch (err) {
            if (typeof Toast !== 'undefined') {Toast.show('✗ 更新失败: ' + err.message);}
        }
    }

    async function confirmDeleteStudent(id) {
        _deletingStudentId = id;
        const student = await StudentService.getRawById(id);
        if (!student) { if (typeof Toast !== 'undefined') {Toast.show('学生不存在');} return; }
        document.getElementById('delete-student-info').textContent = '姓名：' + student.name + '，学号：' + student.no + '，班级：' + student.class;
        document.getElementById('overlay-delete-student').classList.add('open');
    }

    async function submitDeleteStudent() {
        if (!_deletingStudentId) {return;}
        try {
            await StudentService.delete(_deletingStudentId);
            closeModal('delete-student');
            const currentId = Store.getCurrentStudent ? Store.getCurrentStudent() : null;
            if (currentId === _deletingStudentId) {
                document.getElementById('nav-detail').style.display = 'none';
                if (typeof Router !== 'undefined' && Router.navigate) {Router.navigate('students');}
                else if (typeof window.nav === 'function') {window.nav('students');}
            }
            renderList();
            if (typeof Toast !== 'undefined') {Toast.show('✓ 学生档案已删除');}
        } catch (err) {
            if (typeof Toast !== 'undefined') {Toast.show('✗ 删除失败: ' + err.message);}
        }
        _deletingStudentId = null;
    }

    // ══════════════════════════════════════════════════════
    //  公共 API
    // ══════════════════════════════════════════════════════
    return {
        init,
        renderList,
        openDetail,
        renderDetail,
        switchTab,
        renderTab,
        filterStudents,
        setGrade,
        toggleAllergyFilter,
        toggleFpill,
        getFilteredStudents,
        getDisplayName,
        generateAI,
        generateDynamicAI,
        typewriterEffect,
        registerActivity,
        addBook,
        openAddStudent,
        closeModal,
        submitAddStudent,
        openEditStudent,
        submitEditStudent,
        confirmDeleteStudent,
        submitDeleteStudent
    };
})();

window.StudentModule = StudentModule;
