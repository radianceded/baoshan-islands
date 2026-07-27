/**
 * 宝山实验智慧教育平台 - API 数据加载模块
 * 从 Flask API 获取数据，适配前端显示
 */

const API_BASE = ''; // 同源，直接相对路径

// API 工具函数
const API = {
    async get(url) {
        const resp = await fetch(url);
        if (!resp.ok) {throw new Error(resp.statusText);}
        return resp.json();
    },
    
    async post(url, data) {
        const resp = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        if (!resp.ok) {throw new Error(resp.statusText);}
        return resp.json();
    },
    
    // 学生数据
    async getStudents() {
        return this.get('/api/students');
    },
    
    async getStudent(idCard) {
        return this.get(`/api/students/${idCard}`);
    },
    
    async getStats() {
        return this.get('/api/stats');
    },
    
    // 体质数据
    async getFitness(idCard) {
        const url = idCard ? `/api/fitness?id_card=${idCard}` : '/api/fitness';
        return this.get(url);
    },
    
    // 屈光数据
    async getVision(idCard) {
        const url = idCard ? `/api/vision?id_card=${idCard}` : '/api/vision';
        return this.get(url);
    },
    
    // 菜单数据
    async getMenu(week) {
        const url = week ? `/api/menu?week=${week}` : '/api/menu';
        return this.get(url);
    }
};

// 数据转换函数 - 将数据库格式转换为前端格式
function transformStudent(dbStudent) {
    return {
        id: dbStudent.id_card,
        no: dbStudent.id_card,
        name: dbStudent.name,
        grade: dbStudent.grade_name || '未知',
        school: dbStudent.school_name || '宝山实验小学',
        class: dbStudent.class_name || '',
        sex: dbStudent.gender === '男' ? '男' : '女',
        color: getColorByGrade(dbStudent.grade_name),
        avatar: dbStudent.name.charAt(0),
        allergy: [],
        fitness: { items: [] },
        interests: [],
        books: [],
        tags: [],
        awards: []
    };
}

function getColorByGrade(grade) {
    const colors = {
        '一年级': '#C8720A',
        '二年级': '#1E5C3A',
        '三年级': '#0D7377',
        '四年级': '#7C3AED',
        '五年级': '#2563EB',
        '六年级': '#DC2626',
        '初一': '#1E5C3A',
        '初二': '#0D7377',
        '初三': '#7C3AED'
    };
    return colors[grade] || '#0F2546';
}

// 加载所有数据并初始化应用
async function loadAllData() {
    try {
        console.log('正在从API加载数据...');
        
        // 并行加载多个数据源
        const [students, stats, fitness, menu] = await Promise.all([
            API.getStudents().catch(() => []),
            API.getStats().catch(() => ({})),
            API.getFitness().catch(() => []),
            API.getMenu().catch(() => [])
        ]);
        
        console.log('数据加载完成:', {
            students: students.length,
            stats: stats,
            fitness: fitness.length,
            menu: menu.length
        });
        
        // 转换学生数据
        const transformedStudents = students.map(transformStudent);
        
        // 返回全局数据对象
        return {
            students: transformedStudents,
            rawStudents: students,
            stats: stats,
            fitness: fitness,
            menu: menu,
            awards: [],
            clubs: []
        };
        
    } catch (error) {
        console.error('数据加载失败:', error);
        // 返回空数据，使用预设数据
        return null;
    }
}

// 如果API加载失败，使用预设数据
function getFallbackData() {
    // 这会使用HTML中hardcoded的数据
    return null;
}

// 导出全局使用
window.API = API;
window.loadAllData = loadAllData;
window.transformStudent = transformStudent;
