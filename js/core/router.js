/**
 * Router - 视图路由管理
 * 处理侧边栏导航、视图切换、面包屑
 */
const Router = (function() {
    'use strict';
    
    // 视图配置
    const _views = {
        'dashboard': { label: '总览仪表盘', parent: '主控台', icon: '📊' },
        'students':  { label: '学生管理',   parent: '学生管理', icon: '👨‍🎓' },
        'canteen':   { label: '推餐管理',   parent: '学生管理', icon: '🍱' },
        'resources': { label: '教学资源中心', parent: '教学',    icon: '📚' },
        'awards':    { label: '获奖管理',   parent: '学生管理', icon: '🏆' },
        'governance':{ label: '数据治理规则', parent: '系统',    icon: '🛡️' }
    };
    
    // 面包屑导航数据
    const _breadcrumbs = {
        'dashboard': ['首页'],
        'students':  ['首页', '学生管理', '学生列表'],
        'student-detail': ['首页', '学生管理', '学生档案'],
        'canteen':   ['首页', '学生管理', '推餐管理'],
        'resources': ['首页', '教学', '教学资源中心'],
        'awards':    ['首页', '学生管理', '获奖管理'],
        'governance':['首页', '系统', '数据治理规则']
    };
    
    /**
     * 初始化路由
     */
    function init() {
        console.log('[Router] 路由模块初始化完成');
    }
    
    /**
     * 导航到指定视图
     * @param {string} viewId - 目标视图 ID
     * @param {Object} params - 导航参数（如 studentId）
     */
    function navigate(viewId, params) {
        console.log(`[Router] 导航到: ${viewId}`, params || '');
        
        // 隐藏所有视图
        document.querySelectorAll('.view').forEach(v => {
            v.classList.remove('active');
        });
        
        // 显示目标视图
        const targetView = document.getElementById(viewId);
        if (targetView) {
            targetView.classList.add('active');
        }
        
        // 更新侧边栏选中状态
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.remove('active');
        });
        const navKey = viewId === 'student-detail' ? 'students' : viewId;
        const navItem = document.querySelector(`.nav-item[data-view="${navKey}"]`);
        if (navItem) {
            navItem.classList.add('active');
        }
        
        // 更新面包屑
        updateBreadcrumb(viewId, params);
        
        // 更新 Store
        Store.switchView(viewId);
        
        // 触发视图生命周期
        onViewEnter(viewId, params);
    }
    
    /**
     * 更新面包屑
     */
    function updateBreadcrumb(viewId, params) {
        const breadcrumbEl = document.getElementById('breadcrumb');
        if (!breadcrumbEl) {return;}
        
        const crumbs = _breadcrumbs[viewId] || ['首页', viewId];
        
        let html = crumbs.map((crumb, i) => {
            if (i === crumbs.length - 1) {
                return `<span class="current">${crumb}</span>`;
            }
            return `<span>${crumb}</span><span class="sep">›</span>`;
        }).join('');
        
        if (params && params.studentName) {
            html += `<span class="sep">›</span><span class="current">${params.studentName}</span>`;
        }
        
        breadcrumbEl.innerHTML = html;
    }
    
    /**
     * 视图进入时触发的回调
     */
    function onViewEnter(viewId, params) {
        switch (viewId) {
            case 'dashboard':
                if (typeof DashboardModule !== 'undefined' && DashboardModule.refresh) {
                    DashboardModule.refresh();
                }
                break;
            case 'students':
                if (typeof StudentModule !== 'undefined' && StudentModule.renderList) {
                    StudentModule.renderList();
                }
                break;
            case 'student-detail':
                if (typeof StudentModule !== 'undefined' && StudentModule.openDetail) {
                    StudentModule.openDetail(params && params.studentId);
                }
                break;
            case 'awards':
                if (typeof AwardsModule !== 'undefined' && AwardsModule.render) {
                    AwardsModule.render();
                }
                break;
            case 'resources':
                if (typeof ResourceModule !== 'undefined' && ResourceModule.render) {
                    ResourceModule.render();
                }
                break;
        }
    }
    
    /**
     * 获取当前路由
     */
    function getCurrentRoute() {
        return Store.getCurrentView();
    }
    
    // 公共 API
    return {
        init,
        navigate,
        getCurrentRoute,
        updateBreadcrumb
    };
})();

console.log('[Router] 路由模块加载完成');
