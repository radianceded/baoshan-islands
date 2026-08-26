// ══════════════════════════════════════════════════════
//  Resources Module - 资源中心模块
// ══════════════════════════════════════════════════════

const ResourcesModule = (function() {
    'use strict';
    
    // 私有状态
    var _tab = 'teaching';
    var _sub = 'all';
    var _grade = 'all';
    var _selStu = null;
    var _selName = '';
    
    // ══════════════════════════════════════════════════════
    //  初始化资源中心
    // ══════════════════════════════════════════════════════
    function init() {
        // 默认选择第一个学生
        if (typeof STUDENTS !== 'undefined' && STUDENTS.length > 0) {
            _selStu = STUDENTS[0].id;
            _selName = STUDENTS[0].name;
        }
        render();
    }
    
    // ══════════════════════════════════════════════════════
    //  渲染资源中心
    // ══════════════════════════════════════════════════════
    function render() {
        renderTabs();
        renderResources();
        renderStudentSelector();
    }
    
    // ══════════════════════════════════════════════════════
    //  渲染标签栏
    // ══════════════════════════════════════════════════════
    function renderTabs() {
        var tabBar = document.getElementById('res-tab-bar');
        if (!tabBar) {return;}
        
        var tabs = [
            { id: 'teaching', label: '教学设计' },
            { id: 'videos', label: '教学视频' },
            { id: 'questions', label: '练习题' }
        ];
        
        tabBar.innerHTML = tabs.map(function(t) {
            return '<div class="tab' + (t.id === _tab ? ' active' : '') + '" data-tab="' + t.id + '">' + t.label + '</div>';
        }).join('');
        
        // 绑定点击事件
        tabBar.onclick = function(e) {
            var tab = e.target.closest('.tab');
            if (tab) {
                _tab = tab.dataset.tab;
                renderTabs();
                renderResources();
            }
        };
    }
    
    // ══════════════════════════════════════════════════════
    //  渲染资源列表
    // ══════════════════════════════════════════════════════
    function renderResources() {
        var container = document.getElementById('resources-list');
        if (!container) {return;}
        
        var resources = _getResourcesData();
        
        // 应用筛选
        if (_sub !== 'all') {
            resources = resources.filter(function(r) { return r.subject === _sub; });
        }
        if (_grade !== 'all') {
            resources = resources.filter(function(r) { return r.grade === _grade; });
        }
        
        if (resources.length === 0) {
            container.innerHTML = '<div class="empty"><div class="empty-icon">📚</div><div class="empty-title">暂无资源</div><div class="empty-desc">切换筛选条件查看更多资源</div></div>';
            return;
        }
        
        container.innerHTML = resources.map(function(r) {
            return '<div class="card" style="margin-bottom:14px">'
                + '<div class="card-header"><div class="card-title">' + (r.title || r.name) + '</div></div>'
                + '<div class="card-body">'
                + '<div style="font-size:12px;color:var(--ink-3);margin-bottom:8px">'
                + '<span class="badge b-blue">' + r.subject + '</span> '
                + '<span class="badge b-gray">' + r.grade + '</span>'
                + '</div>'
                + '<div style="font-size:13px;color:var(--ink-2);line-height:1.6">' + (r.desc || r.description || '') + '</div>'
                + '</div></div>';
        }).join('');
    }
    
    // ══════════════════════════════════════════════════════
    //  获取资源数据
    // ══════════════════════════════════════════════════════
    function _getResourcesData() {
        // 根据当前标签返回对应资源
        if (_tab === 'teaching') {
            return [
                { id: 'TD001', title: '分数的意义与性质', subject: '数学', grade: '小学五年级', desc: '通过动手操作和实际情境，帮助学生建立分数概念。' },
                { id: 'TD003', title: '光合作用原理', subject: '生物', grade: '初中八年级', desc: '设计对照实验，通过观察与记录深入理解光合作用的本质。' }
            ];
        } else if (_tab === 'videos') {
            return [
                { id: 'V001', title: '分数的世界：从切披萨说起', subject: '数学', grade: '小学五年级', desc: '用生活中切披萨的情境直观讲解分数概念。' },
                { id: 'V002', title: '古诗词诵读：唐诗三百首精选', subject: '语文', grade: '小学四年级', desc: '专业播音员领读，配合意境动画，帮助学生感受诗词韵律美。' }
            ];
        } else if (_tab === 'questions') {
            return [
                { id: 'Q001', title: '分数计算专项练习', subject: '数学', grade: '小学五年级', desc: '涵盖分数加减乘除各类题型，巩固计算能力。' },
                { id: 'Q002', title: '古诗词默写练习', subject: '语文', grade: '小学四年级', desc: '精选必背古诗词，强化记忆与书写。' }
            ];
        }
        return [];
    }
    
    // ══════════════════════════════════════════════════════
    //  渲染学生选择器
    // ══════════════════════════════════════════════════════
    function renderStudentSelector() {
        var sel = document.getElementById('res-student-sel');
        if (!sel) {return;}
        
        var students = (typeof STUDENTS !== 'undefined') ? STUDENTS : [];
        
        sel.innerHTML = '<option value="">选择学生...</option>'
            + students.map(function(s) {
                return '<option value="' + s.id + '"' + (s.id === _selStu ? ' selected' : '') + '>' + s.name + '</option>';
            }).join('');
        
        sel.onchange = function() {
            _selStu = this.value;
            var stu = students.find(function(s) { return s.id === _selStu; });
            _selName = stu ? stu.name : '';
        };
    }
    
    // ══════════════════════════════════════════════════════
    //  生成AI推荐
    // ══════════════════════════════════════════════════════
    function generateAI() {
        if (!_selStu) {
            if (typeof toast === 'function') {toast('请先选择学生');}
            return;
        }
        if (typeof toast === 'function') {toast('正在为 ' + _selName + ' 生成个性化推荐...');}
    }
    
    // ══════════════════════════════════════════════════════
    //  生成试卷
    // ══════════════════════════════════════════════════════
    function generatePaper() {
        if (!_selStu) {
            if (typeof toast === 'function') {toast('请先选择学生');}
            return;
        }
        if (typeof toast === 'function') {toast('正在生成个性化试卷...');}
    }
    
    // ══════════════════════════════════════════════════════
    //  筛选设置
    // ══════════════════════════════════════════════════════
    function setGrade(g) {
        _grade = g;
        renderResources();
    }
    
    function setSubject(s) {
        _sub = s;
        renderResources();
    }
    
    // ══════════════════════════════════════════════════════
    //  学生资源标签页（学生详情中）
    // ══════════════════════════════════════════════════════
    function buildResourcesTab(s) {
        var sn = (typeof getDisplayName === 'function') ? getDisplayName(s) : s.name;
        
        var html = '<div style="padding:18px">'
            + '<div class="notice blue mb14"><span>🎯</span><span>AI 根据 ' + sn + ' 的学习情况推荐以下资源</span></div>'
            + '<div class="g2">';
        
        // 教学设计推荐
        html += '<div class="card"><div class="card-header"><div class="card-title">📖 推荐教学设计</div></div>'
            + '<div class="card-body"><div class="empty"><div class="empty-icon">📚</div>'
            + '<div class="empty-title">点击 AI 生成推荐</div><div class="empty-desc">基于薄弱知识点匹配教学设计</div></div></div></div>';
        
        // 视频推荐
        html += '<div class="card"><div class="card-header"><div class="card-title">🎬 推荐视频</div></div>'
            + '<div class="card-body"><div class="empty"><div class="empty-icon">🎥</div>'
            + '<div class="empty-title">点击 AI 生成推荐</div><div class="empty-desc">匹配薄弱知识点的讲解视频</div></div></div></div>';
        
        html += '</div></div>';
        return html;
    }
    
    // 公共API
    return {
        init: init,
        render: render,
        renderTabs: renderTabs,
        renderResources: renderResources,
        generateAI: generateAI,
        generatePaper: generatePaper,
        setGrade: setGrade,
        setSubject: setSubject,
        buildResourcesTab: buildResourcesTab
    };
})();

// 兼容全局调用
window.ResourcesModule = ResourcesModule;
window.renderResources = ResourcesModule.render;
window.switchResTab = function(el, tab) { ResourcesModule._tab = tab; ResourcesModule.render(); };
window.filterResources = function() { ResourcesModule.renderResources(); };
window.generateResAI = ResourcesModule.generateAI;
window.generatePaper = ResourcesModule.generatePaper;
window.setResGrade = ResourcesModule.setGrade;
window.setResSub = ResourcesModule.setSubject;
window.buildResourcesTab = ResourcesModule.buildResourcesTab;
