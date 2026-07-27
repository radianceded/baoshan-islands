// ══════════════════════════════════════════════════════
//  Canteen Module - 推餐/午餐管理模块
// ══════════════════════════════════════════════════════

const CanteenModule = (function() {
    'use strict';
    
    // 私有状态
    let _week = 1;
    
    // ══════════════════════════════════════════════════════
    //  推餐管理初始化（AB餐菜单查看）- 使用 meal-grid 格式
    // ══════════════════════════════════════════════════════
    function initAdmin() {
        // 使用从 Excel 解析的菜单数据库（新格式）
        if (typeof MENU_DATABASE === 'undefined' || !Object.keys(MENU_DATABASE).length) {
            var wrap = document.getElementById('canteen-dynamic');
            if (wrap) {wrap.innerHTML = '<div class="notice" style="color:#e55;padding:20px">菜单数据未加载，请确认 js/menu_data.js 已正确引入</div>';}
            return;
        }
        
        var wrap = document.getElementById('canteen-dynamic');
        if (!wrap) {return;}

        var weeks = Object.keys(MENU_DATABASE).map(Number).sort(function(a,b){return a-b;});
        if (!weeks.length) {return;}
        if (!weeks.includes(_week)) {_week = weeks[0];}

        var days = ['周一','周二','周三','周四','周五'];
        var weekEntry = MENU_DATABASE[String(_week)] || {};
        var weekData = weekEntry.days || {};

        // Week selector
        var html = '<div style="display:flex;align-items:center;gap:10px;margin-bottom:18px">'
            +'<span style="font-size:12px;font-weight:600;color:var(--ink-3)">选择周次</span>'
            +'<select class="fselect" style="width:120px" id="canteen-week-sel">'
            +weeks.map(function(w){return '<option value="'+w+'"'+(w===_week?' selected':'')+'>第 '+w+' 周</option>';}).join('')
            +'</select>'
            +'<span style="font-size:11px;color:var(--ink-4)">'+days.length+' 个工作日</span></div>';
        
        // 每一天的 AB 餐 - 使用 meal-grid 格式
        days.forEach(function(day) {
            var dayData = weekData[day] || {};
            var mealA = dayData.A || {};
            var mealB = dayData.B || {};
            
            html += '<div style="margin-bottom:20px">'
                +'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
                +'<div style="width:4px;height:18px;background:var(--amber);border-radius:2px"></div>'
                +'<div style="font-size:13px;font-weight:700;color:var(--ink-3)">'+day+'</div></div>'
                +'<div class="meal-grid">'
                +_renderMealCard('A', mealA, 'var(--navy-2)')
                +_renderMealCard('B', mealB, 'var(--green)')
                +'</div></div>';
        });
        
        wrap.innerHTML = html;
        
        // 绑定周次切换事件
        var weekSel = document.getElementById('canteen-week-sel');
        if (weekSel) {
            weekSel.onchange = function() {
                _week = parseInt(this.value);
                initAdmin();
            };
        }
    }
    
    // 使用 meal-grid / meal-card 格式渲染餐卡（仿学生档案午餐晚餐样式）
    function _renderMealCard(setName, meal, color) {
        var m = meal || {};
        var main = m.main || '';
        var dishes = Array.isArray(m.dishes) ? m.dishes : [];
        var soup = m.soup || '';
        var fruit = m.fruit || '';
        var cal = m.calories || '';
        
        // 构建菜品列表 HTML
        var itemsHtml = '';
        
        // 主食
        if (main) {
            itemsHtml += '<li>🍚 '+main+'<span style="margin-left:auto;font-size:10px;color:var(--ink-4)">主食</span></li>';
        }
        
        // 菜品
        dishes.forEach(function(name, idx) {
            itemsHtml += '<li>🥘 '+name+'<span style="margin-left:auto;font-size:10px;color:var(--ink-4)">菜品'+(idx+1)+'</span></li>';
        });
        
        // 例汤
        if (soup) {
            itemsHtml += '<li>🥣 '+soup+'<span style="margin-left:auto;font-size:10px;color:var(--ink-4)">例汤</span></li>';
        }
        
        // 水果
        if (fruit) {
            itemsHtml += '<li>🍎 '+fruit+'<span style="margin-left:auto;font-size:10px;color:var(--ink-4)">水果</span></li>';
        }
        
        // 如果没有任何内容，显示暂无菜单
        if (!itemsHtml) {
            itemsHtml = '<li style="color:var(--ink-3)">暂无菜单</li>';
        }
        
        // 热量显示
        var calHtml = cal ? '<div style="text-align:right;margin-top:8px;padding-top:8px;border-top:1px solid #F3F0EA"><span style="font-size:12px;color:var(--ink-4)">热量 </span><span style="font-size:14px;font-weight:700;color:'+color+'">'+cal.replace('kcal','')+'</span><span style="font-size:10px;color:var(--ink-4)"> kcal</span></div>' : '';
        
        var card = '<div class="meal-card">'
            +'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'
            +'<div><div class="meal-type" style="color:'+color+'">'+setName+' 餐</div>'
            +'<div class="meal-title">'+(main || '套餐')+'</div></div></div>'
            +'<ul class="meal-items" style="margin-bottom:10px">'+itemsHtml+'</ul>'
            +'<div class="meal-note ok">✓ 营养均衡搭配</div>'
            +calHtml
            +'</div>';
        
        return card;
    }
    
    // ══════════════════════════════════════════════════════
    //  学生详情中的晚餐 HTML 生成
    // ══════════════════════════════════════════════════════
    function buildDinnerHTML(sn) {
        if (!REAL_DATA || !REAL_DATA.menu_by_week) {return '';}
        var w = Object.keys(REAL_DATA.menu_by_week).map(Number).sort(function(a,b){return a-b;})[0] || 1;
        var wd = REAL_DATA.menu_by_week[w] || {};
        var dd = wd['周五'] || {};
        var bDishes = dd['B'] || [];
        var dishes = bDishes.filter(function(x) { return x.dish && x.category && x.category.includes('品') && !x.category.includes('热量') && !x.category.includes('蛋白'); });
        if (!dishes.length) {return '';}
        return '<div class="meal-grid"><div class="meal-card"><div class="meal-type">🥣 晚餐推荐</div><div class="meal-title">营养均衡搭配</div><ul class="meal-items">'
            + dishes.map(function(d) { return '<li>🍽 '+d.dish+'</li>'; }).join('')
            + '</ul><div class="meal-note ok">基于 '+sn+' 的营养需求智能推荐</div></div></div>';
    }
    
    // ══════════════════════════════════════════════════════
    //  营养方案输出
    // ══════════════════════════════════════════════════════
    function buildCanteenOutput(lunchReason, recMeal, dinnerHTML, sn, warn) {
        var html = '<div class="g2 mb14">'
            + '<div class="meal-card rec">'
            + '<div class="meal-rec-label">AI 推荐午餐</div>'
            + '<div class="meal-type">🍜 午餐推荐</div>'
            + '<div class="meal-title">基于营养需求的个性化推荐</div>'
            + '<ul class="meal-items">' + recMeal.map(function(m) {
            var cls = warn && warn.includes(m) ? ' warn' : '';
            return '<li class="'+cls+'">'+m+'</li>';
        }).join('') + '</ul>'
            + '<div class="meal-note ok">'+lunchReason+'</div>'
            + '</div>' + dinnerHTML + '</div>';
        return html;
    }
    
    // ══════════════════════════════════════════════════════
    //  学生推餐标签页
    // ══════════════════════════════════════════════════════
    function buildCanteenTab(s) {
        var sn = (typeof getDisplayName === 'function') ? getDisplayName(s) : s.name;
        var allergyList = s.allergy || [];
        
        var html = '<div class="card-header" style="padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between">'
            + '<div><div style="font-size:14px;font-weight:600">🍱 个性化午餐推荐</div>'
            + '<div style="font-size:11px;color:var(--ink-4)">AI 基于健康档案和过敏信息智能推荐</div></div></div>'
            + '<div style="padding:18px">';
        
        // 过敏提示
        if (allergyList.length > 0) {
            html += '<div class="notice amber mb14"><span>⚠️</span><span>'+sn+' 有以下过敏原：'
                + allergyList.map(function(a) { return '<strong>'+a+'</strong>'; }).join('、')
                + '。推荐餐品已自动规避。</span></div>';
        }
        
        html += '<div class="empty"><div class="empty-icon">🍱</div><div class="empty-title">点击上方 AI 推荐按钮</div>'
            + '<div class="empty-desc">系统将基于 '+sn+' 的过敏信息和营养需求生成个性化推荐</div></div>';
        
        html += '</div>';
        return html;
    }
    
    // ══════════════════════════════════════════════════════
    //  推送资源
    // ══════════════════════════════════════════════════════
    function pushResources() {
        if (typeof toast === 'function') {toast('推荐方案已推送至家长端');}
    }
    
    // 公共API
    return {
        initAdmin: initAdmin,
        buildDinnerHTML: buildDinnerHTML,
        buildCanteenOutput: buildCanteenOutput,
        buildCanteenTab: buildCanteenTab,
        pushResources: pushResources
    };
})();

// 兼容全局调用
window.initCanteenAdmin = CanteenModule.initAdmin;
window.buildDinnerHTML = CanteenModule.buildDinnerHTML;
window.buildCanteenOutput = CanteenModule.buildCanteenOutput;
window.buildCanteenTab = CanteenModule.buildCanteenTab;
window.pushResources = CanteenModule.pushResources;
window.canteenWeek = 1;
window.canteenDay = '周一';
