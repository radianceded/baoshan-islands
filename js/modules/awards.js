// ══════════════════════════════════════════════════════
//  Awards Module - 获奖管理模块
// ══════════════════════════════════════════════════════

const AwardsModule = (function() {
    'use strict';
    
    // 私有状态
    var _filter = 'all';
    
    // ══════════════════════════════════════════════════════
    //  初始化获奖管理视图
    // ══════════════════════════════════════════════════════
    function initView() {
        renderAwardsTable();
        renderAnalytics();
        renderCharts();
    }
    
    // ══════════════════════════════════════════════════════
    //  渲染获奖表格
    // ══════════════════════════════════════════════════════
    function renderAwardsTable() {
        var tbody = document.getElementById('awards-tbody');
        if (!tbody) {return;}
        
        var awards = _getAwardsData();
        
        // 应用筛选
        if (_filter !== 'all') {
            awards = awards.filter(function(a) { return a.level === _filter || a.subject === _filter; });
        }
        
        if (awards.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty"><div class="empty-icon">🏆</div><div class="empty-title">暂无获奖记录</div></td></tr>';
            return;
        }
        
        tbody.innerHTML = awards.map(function(a) {
            var levelBadge = _getLevelBadge(a.level);
            return '<tr>'
                + '<td>' + (a.student_name || '-') + '</td>'
                + '<td>' + (a.competition || a.name || '-') + '</td>'
                + '<td>' + (a.subject || '-') + '</td>'
                + '<td>' + levelBadge + '</td>'
                + '<td>' + (a.prize || '-') + '</td>'
                + '<td>' + (a.date || '-') + '</td>'
                + '</tr>';
        }).join('');
    }
    
    // ══════════════════════════════════════════════════════
    //  获取获奖数据
    // ══════════════════════════════════════════════════════
    function _getAwardsData() {
        if (typeof REAL_DATA !== 'undefined' && REAL_DATA.awards_by_student) {
            // 从 REAL_DATA 解析
            var awards = [];
            Object.keys(REAL_DATA.awards_by_student).forEach(function(studentName) {
                var studentAwards = REAL_DATA.awards_by_student[studentName] || [];
                studentAwards.forEach(function(a) {
                    awards.push({
                        student_name: studentName,
                        competition: a.competition || a.name,
                        subject: a.subject,
                        level: a.level,
                        prize: a.prize,
                        date: a.date,
                        org: a.org
                    });
                });
            });
            return awards;
        }
        // 默认数据
        return [
            { student_name: '徐雨萱', competition: '2024年"文新杯"现场作文比赛', subject: '语文', level: '区级', prize: '二等奖', date: '2024.12' },
            { student_name: '高祎晗', competition: '宝山区少儿书画作品征集活动', subject: '美术', level: '区级', prize: '三等奖', date: '2024.09' }
        ];
    }
    
    // ══════════════════════════════════════════════════════
    //  获取级别徽章HTML
    // ══════════════════════════════════════════════════════
    function _getLevelBadge(level) {
        var badgeClass = 'b-gray';
        if (level === '国家级') {badgeClass = 'b-red';}
        else if (level === '市级') {badgeClass = 'b-purple';}
        else if (level === '区级') {badgeClass = 'b-blue';}
        else if (level === '校级') {badgeClass = 'b-green';}
        return '<span class="badge ' + badgeClass + '">' + level + '</span>';
    }
    
    // ══════════════════════════════════════════════════════
    //  渲染统计分析
    // ══════════════════════════════════════════════════════
    function renderAnalytics() {
        var awards = _getAwardsData();
        var container = document.getElementById('awards-analytics');
        if (!container) {return;}
        
        // 统计各科目数量
        var subjectCount = {};
        var levelCount = {};
        
        awards.forEach(function(a) {
            subjectCount[a.subject] = (subjectCount[a.subject] || 0) + 1;
            levelCount[a.level] = (levelCount[a.level] || 0) + 1;
        });
        
        var html = '<div class="g3">';
        
        // 科目分布
        html += '<div class="card"><div class="card-header"><div class="card-title">📊 学科分布</div></div><div class="card-body">';
        Object.keys(subjectCount).forEach(function(subj) {
            html += '<div class="prog-item"><div class="prog-label"><span class="prog-name">' + subj + '</span><span class="prog-val">' + subjectCount[subj] + '</span></div>'
                + '<div class="prog-bar"><div class="prog-fill" style="width:' + Math.min(100, subjectCount[subj] * 10) + '%;background:var(--navy-2)"></div></div></div>';
        });
        html += '</div></div>';
        
        // 级别分布
        html += '<div class="card"><div class="card-header"><div class="card-title">🏆 级别分布</div></div><div class="card-body">';
        Object.keys(levelCount).forEach(function(lv) {
            html += '<div class="prog-item"><div class="prog-label"><span class="prog-name">' + lv + '</span><span class="prog-val">' + levelCount[lv] + '</span></div>'
                + '<div class="prog-bar"><div class="prog-fill" style="width:' + Math.min(100, levelCount[lv] * 10) + '%;background:var(--green)"></div></div></div>';
        });
        html += '</div></div>';
        
        // 总览
        html += '<div class="card"><div class="card-header"><div class="card-title">📈 获奖总览</div></div><div class="card-body">'
            + '<div style="text-align:center;padding:20px 0">'
            + '<div style="font-size:36px;font-weight:700;color:var(--navy-2)">' + awards.length + '</div>'
            + '<div style="font-size:13px;color:var(--ink-4)">总获奖数</div>'
            + '</div></div></div>';
        
        html += '</div>';
        container.innerHTML = html;
    }
    
    // ══════════════════════════════════════════════════════
    //  渲染图表
    // ══════════════════════════════════════════════════════
    function renderCharts() {
        var container = document.getElementById('awards-charts');
        if (!container) {return;}
        
        // 简单的月度趋势展示
        container.innerHTML = '<div class="card"><div class="card-header"><div class="card-title">📅 获奖趋势</div></div>'
            + '<div class="card-body"><div style="height:200px;display:flex;align-items:center;justify-content:center;color:var(--ink-4)">'
            + '图表功能开发中...</div></div></div>';
    }
    
    // ══════════════════════════════════════════════════════
    //  设置筛选条件
    // ══════════════════════════════════════════════════════
    function setFilter(filter) {
        _filter = filter;
        renderAwardsTable();
    }
    
    // ══════════════════════════════════════════════════════
    //  获奖标签页（学生详情中）
    // ══════════════════════════════════════════════════════
    function buildAwardsTab(s) {
        var sn = (typeof getDisplayName === 'function') ? getDisplayName(s) : s.name;
        var awards = (s.awards || []);
        
        var html = '<div style="padding:18px">';
        
        if (awards.length === 0) {
            html += '<div class="empty"><div class="empty-icon">🏆</div><div class="empty-title">暂无获奖记录</div>'
                + '<div class="empty-desc">' + sn + ' 还没有录入获奖信息</div></div>';
        } else {
            html += '<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px">';
            awards.forEach(function(a) {
                var badgeClass = _getLevelBadge(a.level);
                html += '<div class="card" style="flex:1;min-width:280px">'
                    + '<div class="card-body">'
                    + '<div style="font-size:13px;font-weight:600;margin-bottom:6px">' + (a.competition || a.name) + '</div>'
                    + '<div style="display:flex;gap:6px;margin-bottom:8px">'
                    + badgeClass + ' <span class="badge b-outline">' + (a.prize || '-') + '</span>'
                    + '</div>'
                    + '<div style="font-size:12px;color:var(--ink-4)">' + (a.subject || '-') + ' · ' + (a.date || '-') + '</div>'
                    + '</div></div>';
            });
            html += '</div>';
            
            html += '<div class="callout blue"><span>🏆</span><span>' + sn + ' 共获得 ' + awards.length + ' 项荣誉，点击导出可生成获奖证明</span></div>';
        }
        
        html += '</div>';
        return html;
    }
    
    // ══════════════════════════════════════════════════════
    //  获奖行渲染（用于列表）
    // ══════════════════════════════════════════════════════
    function renderAwardRow(award) {
        return '<div class="card" style="margin-bottom:10px">'
            + '<div class="card-body">'
            + '<div style="display:flex;justify-content:space-between;align-items:center">'
            + '<div><div style="font-size:13px;font-weight:600">' + award.competition + '</div>'
            + '<div style="font-size:12px;color:var(--ink-4)">' + award.subject + ' · ' + award.date + '</div></div>'
            + '<div>' + _getLevelBadge(award.level) + '</div>'
            + '</div></div></div>';
    }
    
    // ══════════════════════════════════════════════════════
    //  级别徽章渲染
    // ══════════════════════════════════════════════════════
    function levelPill(level) {
        return _getLevelBadge(level);
    }
    
    function prizePill(prize) {
        return '<span class="badge b-outline">' + prize + '</span>';
    }
    
    // 公共API
    return {
        initView: initView,
        renderAwardsTable: renderAwardsTable,
        renderAnalytics: renderAnalytics,
        renderCharts: renderCharts,
        setFilter: setFilter,
        buildAwardsTab: buildAwardsTab,
        renderAwardRow: renderAwardRow,
        levelPill: levelPill,
        prizePill: prizePill
    };
})();

// 兼容全局调用
window.initAwardsView = AwardsModule.initView;
window.renderAwardsTable = AwardsModule.renderAwardsTable;
window.renderAwardCharts = AwardsModule.renderCharts;
window.setAwFilter = AwardsModule.setFilter;
window.buildAwardsTab = AwardsModule.buildAwardsTab;
window.levelPill = AwardsModule.levelPill;
window.prizePill = AwardsModule.prizePill;
