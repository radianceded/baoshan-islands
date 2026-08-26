// ══════════════════════════════════════════════════════
//  Dashboard Module - 仪表盘模块
// ══════════════════════════════════════════════════════

const DashboardModule = (function() {
    'use strict';
    
    // 私有变量
    let _feedRendered = false;
    let _logRendered = false;
    
    // ══════════════════════════════════════════════════════
    //  仪表盘初始化
    // ══════════════════════════════════════════════════════
    function init() {
        console.log('初始化仪表盘, 学生数:', typeof STUDENTS !== 'undefined' ? STUDENTS.length : 0);
        try {
            // 更新 KPI 数字
            const totalEl = document.getElementById('kpi-total');
            const activeEl = document.getElementById('kpi-active');
            const pendingEl = document.getElementById('kpi-pending');
            
            if (totalEl && typeof STUDENTS !== 'undefined') {
                totalEl.textContent = STUDENTS.length || 0;
            }
            if (activeEl) {
                activeEl.textContent = typeof STUDENTS !== 'undefined' ? Math.floor((STUDENTS.length || 0) * 0.92) : 0;
            }
            if (pendingEl) {
                pendingEl.textContent = typeof STUDENTS !== 'undefined' ? Math.floor((STUDENTS.length || 0) * 0.08) : 0;
            }
            
            // 渲染今日动态
            if (!_feedRendered) {
                renderFeed();
                _feedRendered = true;
            }
            
            // 渲染通知日志
            if (!_logRendered) {
                renderLog();
                _logRendered = true;
            }
            
            console.log('仪表盘初始化完成');
        } catch (err) {
            console.error('仪表盘初始化失败:', err);
        }
    }
    
    // ══════════════════════════════════════════════════════
    //  渲染今日动态
    // ══════════════════════════════════════════════════════
    function renderFeed() {
        const feedEl = document.getElementById('dashboard-feed');
        if (!feedEl) {return;}
        
        const feedItems = [
            { icon: '📊', title: '体质健康', desc: '已完成本学期体质健康数据采集', time: '10:23' },
            { icon: '🍱', title: '营养餐推送', desc: '已向35位家长推送个性化营养建议', time: '09:45' },
            { icon: '🏆', title: '获奖记录', desc: '新增12条学生获奖记录已录入', time: '09:12' },
            { icon: '📚', title: '阅读推荐', desc: 'AI阅读推荐系统更新完成', time: '08:56' }
        ];
        
        feedEl.innerHTML = feedItems.map(item => `
            <div class="feed-item">
                <div class="feed-icon" style="background:var(--blue-light)">${item.icon}</div>
                <div>
                    <div class="feed-title">${item.title}</div>
                    <div style="font-size:12px;color:var(--ink-3)">${item.desc}</div>
                    <div class="feed-time">${item.time}</div>
                </div>
            </div>
        `).join('');
    }
    
    // ══════════════════════════════════════════════════════
    //  渲染通知日志
    // ══════════════════════════════════════════════════════
    function renderLog() {
        const logEl = document.getElementById('dashboard-log');
        if (!logEl) {return;}
        
        const logItems = [
            { time: '10:15', event: '系统', desc: '自动备份完成' },
            { time: '09:30', event: '推餐', desc: '早餐推荐已推送' },
            { time: '08:45', event: '体测', desc: '三年级体质数据导入' },
            { time: '08:00', event: '系统', desc: '日常数据同步完成' }
        ];
        
        logEl.innerHTML = logItems.map(item => `
            <div style="display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #F3F0EA;font-size:12px">
                <span style="color:var(--ink-4);min-width:45px">${item.time}</span>
                <span style="color:var(--navy-2);font-weight:500;min-width:50px">${item.event}</span>
                <span style="color:var(--ink-3)">${item.desc}</span>
            </div>
        `).join('');
    }
    
    // ══════════════════════════════════════════════════════
    //  场景卡片点击处理
    // ══════════════════════════════════════════════════════
    function onSceneCardClick(sceneType) {
        switch(sceneType) {
            case 'canteen':
                window.nav && window.nav('canteen');
                break;
            case 'student':
                window.nav && window.nav('students');
                break;
            case 'resources':
                window.nav && window.nav('resources');
                break;
            case 'awards':
                window.nav && window.nav('awards');
                break;
            default:
                window.toast && window.toast('功能开发中...');
        }
    }
    
    // 公共API
    return {
        init: init,
        renderFeed: renderFeed,
        renderLog: renderLog,
        onSceneCardClick: onSceneCardClick
    };
})();

// 兼容全局调用
window.initDashboard = DashboardModule.init;
window.renderFeed = DashboardModule.renderFeed;
window.renderLog = DashboardModule.renderLog;
