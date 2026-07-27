/**
 * 应用主入口模块
 * 负责数据加载、应用初始化和全局视图刷新
 */

// ══════════════════════════════════════════════════════
//  全局数据状态
// ══════════════════════════════════════════════════════
let STUDENTS = [];
let REAL_DATA = {
    awards_by_student: {},
    clubs_by_student: {},
    menu_by_week: {},
    fitness_history: []
};
let DATA_LOADED = false;

// ══════════════════════════════════════════════════════
//  数据加载功能
// ══════════════════════════════════════════════════════

/**
 * 异步加载真实数据（从 data.json）
 * @returns {Promise<boolean>}
 */
async function loadRealData() {
    try {
        Toast.show('正在加载学生数据...', 'info');
        console.log('正在加载学生数据...');

        let data;
        try {
            const response = await fetch('data.json');
            if (!response.ok) {throw new Error(`HTTP ${response.status}`);}
            data = await response.json();
            console.log('从 data.json 加载成功');
        } catch (fetchErr) {
            console.warn('fetch data.json 失败:', fetchErr.message);
            const cached = localStorage.getItem('uniedu_students_data');
            if (cached) {
                data = JSON.parse(cached);
                console.log('从 localStorage 加载成功');
            } else {
                throw new Error('无法加载数据，请确保 data.json 文件存在');
            }
        }

        STUDENTS = data.students || [];
        REAL_DATA = {
            awards_by_student: data.awards_by_student || {},
            clubs_by_student: data.clubs_by_student || {},
            menu_by_week: data.menu_by_week || {},
            fitness_history: data.fitness_history || []
        };
        DATA_LOADED = true;
        console.log(`数据加载完成: ${STUDENTS.length}名学生`);

        try {
            localStorage.setItem('uniedu_students_data', JSON.stringify(data));
        } catch (e) { /* ignore */ }

        Store.setStudents(STUDENTS);
        await initStudentServiceWithRealData();
        refreshCurrentView();
        Toast.show(`数据加载完成: ${STUDENTS.length}名学生`, 'success');
        return true;
    } catch (error) {
        console.error('加载数据失败:', error);
        Toast.show('数据加载失败: ' + error.message, 'error');
        return false;
    }
}

/**
 * 初始化学生服务层
 */
async function initStudentServiceWithRealData() {
    try {
        console.log('开始初始化学生服务...');
        if (typeof StudentService === 'undefined') {
            console.warn('StudentService 未定义，跳过');
            return;
        }
        await StudentService.init();
        const existing = await StudentService.list();
        if (existing.length > 0) {await StudentService.clear();}
        if (STUDENTS.length > 0) {
            const result = await StudentService.importFromArray(STUDENTS);
            if (result.errors && result.errors.length > 0) {
                console.error('导入错误:', result.errors);
            }
        }
        console.log('学生服务层初始化完成');
    } catch (err) {
        console.error('initStudentServiceWithRealData 失败:', err);
    }
}

/**
 * 刷新当前视图
 */
function refreshCurrentView() {
    const currentView = document.querySelector('.view.active');
    if (!currentView) {return;}
    const viewId = currentView.id;
    const handlers = {
        'students': () => StudentModule && StudentModule.renderList && StudentModule.renderList(),
        'dashboard': () => DashboardModule && DashboardModule.refresh && DashboardModule.refresh(),
        'awards': () => AwardsModule && AwardsModule.render && AwardsModule.render(),
        'resources': () => ResourceModule && ResourceModule.render && ResourceModule.render(),
        'canteen': () => CanteenModule && CanteenModule.render && CanteenModule.render()
    };
    if (handlers[viewId]) {handlers[viewId]();}
    else if (viewId === 'student-detail') {
        const activeRow = document.querySelector('.student-row.active');
        if (activeRow && StudentModule && StudentModule.openDetail) {
            StudentModule.openDetail(activeRow.dataset.id);
        }
    }
}

/**
 * 应用初始化
 */
async function initApp() {
    const now = new Date();
    const headerDate = document.getElementById('header-date');
    if (headerDate) {
        headerDate.textContent = `${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日 周${'日一二三四五六'[now.getDay()]}`;
    }
    if (!DATA_LOADED || STUDENTS.length === 0) {
        await loadRealData();
    }
    try {
        if (typeof StudentService !== 'undefined') {
            await StudentService.init();
            const list = await StudentService.list();
            if (list.length === 0 && STUDENTS.length > 0) {
                await StudentService.importFromArray(STUDENTS);
            }
        }
    } catch (err) { console.warn('StudentService初始化失败:', err); }
    console.log('应用初始化完成，学生数:', STUDENTS.length);
}

// ══════════════════════════════════════════════════════
//  应用启动
// ══════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', async () => {
    console.log('应用初始化...');
    console.log('StudentService 状态:', typeof StudentService !== 'undefined' ? '已加载' : '未加载');

    // 强制重置模式
    if (window.location.search.includes('reset=1')) {
        console.log('强制重置模式...');
        try {
            if (typeof StudentService !== 'undefined' && StudentService.clear) {await StudentService.clear();}
            localStorage.removeItem('uniedu_students_data');
            Toast.show('数据已重置', 'info');
        } catch (e) { console.error('重置失败:', e); }
    }

    // 加载数据
    await loadRealData();

    // 初始化核心模块
    if (typeof Store !== 'undefined' && Store.init) {Store.init();}
    if (typeof Router !== 'undefined' && Router.init) {Router.init();}
    if (typeof Toast !== 'undefined' && Toast.init) {Toast.init();}

    // 初始化业务模块
    if (typeof StudentModule !== 'undefined' && StudentModule.init) {StudentModule.init();}
    if (typeof DashboardModule !== 'undefined' && DashboardModule.init) {DashboardModule.init();}
    if (typeof CanteenModule !== 'undefined' && CanteenModule.init) {CanteenModule.init();}
    if (typeof ResourceModule !== 'undefined' && ResourceModule.init) {ResourceModule.init();}
    if (typeof AwardsModule !== 'undefined' && AwardsModule.init) {AwardsModule.init();}

    // 导航到默认视图
    if (typeof Router !== 'undefined') {
        Router.navigate('dashboard');
    }

    console.log('[App] 应用启动完成');
});

console.log('[App] 应用主入口模块加载完成');
