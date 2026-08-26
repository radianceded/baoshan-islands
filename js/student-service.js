/**
 * StudentService - 学生数据服务层
 * 
 * 核心功能：
 * 1. IndexedDB持久化存储（解决刷新数据丢失问题）
 * 2. 统一去敏中间件（隐私保护）
 * 3. API层模拟（为后续接入后端做准备）
 * 4. CRUD操作封装
 */

// ══════════════════════════════════════════════════════
//  1. 配置层
// ══════════════════════════════════════════════════════
const StudentConfig = {
    // 去敏配置
    anonymization: {
        enabled: true,
        mode: 'mask', // 'mask': 张三→张**, 'initial': 张三→张*
        cache: new Map() // 姓名去敏缓存
    },
    // 学号校验规则
    validation: {
        idPattern: /^[A-Z]{1,2}\d{3,20}$/, // 兼容学号如 BS2024001 (2字母+7位数字)、身份证号如 G<student-id>
        maxNameLength: 20,
        requiredFields: ['name', 'no', 'school', 'class']
    },
    // 数据库配置
    db: {
        name: 'StudentDB',
        version: 1
    }
};

// ══════════════════════════════════════════════════════
//  2. 去敏工具函数
// ══════════════════════════════════════════════════════
const Anonymizer = {
    /**
     * 对姓名进行去敏处理
     * @param {string} realName - 真实姓名
     * @returns {string} - 去敏后的姓名
     */
    maskName(realName) {
        if (!realName || realName.length === 0) {return '';}
        if (!StudentConfig.anonymization.enabled) {return realName;}
        
        // 检查缓存
        if (StudentConfig.anonymization.cache.has(realName)) {
            return StudentConfig.anonymization.cache.get(realName);
        }
        
        let masked;
        if (StudentConfig.anonymization.mode === 'mask') {
            // 张三 → 张**
            const first = realName.charAt(0);
            masked = first + '*'.repeat(Math.max(1, realName.length - 1));
        } else {
            // 张三 → 张*
            masked = realName.charAt(0) + '*';
        }
        
        StudentConfig.anonymization.cache.set(realName, masked);
        return masked;
    },

    /**
     * 批量去敏学生数据
     * @param {Object|Array} data - 学生数据
     * @returns {Object|Array} - 去敏后的数据
     */
    sanitize(data) {
        if (Array.isArray(data)) {
            return data.map(s => this.sanitizeStudent(s));
        }
        return this.sanitizeStudent(data);
    },

    /**
     * 去敏单个学生对象
     */
    sanitizeStudent(student) {
        if (!student) {return null;}
        
        return {
            ...student,
            displayName: this.maskName(student.name),
            // 保留真实姓名供内部使用，但不对外暴露
            _realName: student.name,
            // AI Prompt使用ID替代姓名
            aiPromptName: `学生ID:${student.id}`
        };
    },

    /**
     * 切换去敏状态
     */
    toggle() {
        StudentConfig.anonymization.enabled = !StudentConfig.anonymization.enabled;
        StudentConfig.anonymization.cache.clear();
        return StudentConfig.anonymization.enabled;
    },

    /**
     * 获取当前去敏状态
     */
    isEnabled() {
        return StudentConfig.anonymization.enabled;
    }
};

// ══════════════════════════════════════════════════════
//  3. IndexedDB 数据库层 (使用 Dexie.js)
// ══════════════════════════════════════════════════════
let db = null;

/**
 * 初始化数据库
 */
function initDatabase() {
    if (db) {return db;}
    
    // 检查 Dexie 是否加载
    if (typeof Dexie === 'undefined') {
        console.warn('Dexie.js 未加载，将使用内存存储模式');
        return null;
    }
    
    db = new Dexie(StudentConfig.db.name);
    
    db.version(StudentConfig.db.version).stores({
        students: '++id, no, name, grade, school, class, createdAt, updatedAt, deleted',
        syncQueue: '++autoId, action, tableName, data, timestamp, retryCount'
    });
    
    // 打开数据库
    return db.open().then(() => {
        console.log('StudentDB 已连接');
        return db;
    }).catch(err => {
        console.error('数据库连接失败:', err);
        return null;
    });
}

// ══════════════════════════════════════════════════════
//  4. 数据校验层
// ══════════════════════════════════════════════════════
const Validator = {
    /**
     * 校验学生数据
     */
    validate(studentData) {
        const errors = [];
        const { validation } = StudentConfig;
        
        // 必填字段检查
        validation.requiredFields.forEach(field => {
            if (!studentData[field]) {
                errors.push(`缺少必填字段: ${field}`);
            }
        });
        
        // 姓名长度检查
        if (studentData.name && studentData.name.length > validation.maxNameLength) {
            errors.push(`姓名长度超过 ${validation.maxNameLength} 字符`);
        }
        
        // 学号格式检查
        if (studentData.no && !validation.idPattern.test(studentData.no)) {
            errors.push('学号格式不正确（如：BS2024001）');
        }
        
        // 年龄合理性检查
        if (studentData.age && (studentData.age < 3 || studentData.age > 25)) {
            errors.push('年龄应在 3-25 岁之间');
        }
        
        if (errors.length > 0) {
            throw new Error(errors.join('; '));
        }
        
        return true;
    },

    /**
     * 生成默认字段
     */
    enrich(studentData) {
        const colors = ['#C8720A', '#1E5C3A', '#0D7377', '#7C3AED', '#DC2626', '#16A34A', '#D97706', '#0891B2', '#EA580C', '#2563EB'];
        
        return {
            ...studentData,
            id: studentData.id || ('stu_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6)),
            color: studentData.color || colors[Math.floor(Math.random() * colors.length)],
            avatar: studentData.name ? studentData.name.charAt(0) : '学',
            createdAt: studentData.createdAt || Date.now(),
            updatedAt: Date.now(),
            deleted: false,
            // 默认空值
            allergy: studentData.allergy || [],
            interests: studentData.interests || ['阅读'],
            books: studentData.books || [],
            awards: studentData.awards || [],
            tags: studentData.tags || ['新添加学生'],
            fitness: studentData.fitness || {
                items: [
                    {e:'🏃',n:'50米跑',s:'fair'},{e:'🤸',n:'坐位体前屈',s:'fair'},
                    {e:'💪',n:'体能测试',s:'fair'},{e:'🫁',n:'肺活量',s:'fair'},
                    {e:'⏱',n:'耐力跑',s:'fair'},{e:'🦵',n:'立定跳远',s:'fair'}
                ]
            }
        };
    }
};

// ══════════════════════════════════════════════════════
//  5. 学生服务主类
// ══════════════════════════════════════════════════════
const StudentService = {
    // 内存缓存（Dexie不可用时降级）
    _memoryCache: [],
    _initialized: false,
    
    /**
     * 初始化服务
     */
    async init() {
        if (this._initialized) {return;}
        
        // 尝试连接 IndexedDB
        const database = await initDatabase();
        
        if (database) {
            // 从 IndexedDB 加载数据到内存缓存
            const students = await db.students.where('deleted').equals(0).toArray();
            this._memoryCache = students;
        }
        
        this._initialized = true;
        console.log(`StudentService 初始化完成，加载 ${this._memoryCache.length} 名学生`);
    },

    // ═════════════════════════════════════════════════
    //  CRUD 操作
    // ═════════════════════════════════════════════════
    
    /**
     * 创建学生
     * @param {Object} data - 学生数据
     * @returns {Promise<Object>} - 创建后的学生（含去敏）
     */
    async create(data) {
        // 1. 校验
        Validator.validate(data);
        
        // 2. 查重（学号）
        const exists = await this.findByNo(data.no);
        if (exists) {
            throw new Error(`学号 ${data.no} 已存在`);
        }
        
        // 3. 填充默认值
        const enriched = Validator.enrich(data);
        
        // 4. 保存到 IndexedDB
        if (db) {
            await db.students.add(enriched);
        }
        
        // 5. 更新内存缓存
        this._memoryCache.push(enriched);
        
        // 6. 加入同步队列（为后续接入后端做准备）
        if (db) {
            await db.syncQueue.add({
                action: 'create',
                tableName: 'students',
                data: enriched,
                timestamp: Date.now(),
                retryCount: 0
            });
        }
        
        // 7. 返回去敏版本
        return Anonymizer.sanitizeStudent(enriched);
    },

    /**
     * 查询所有学生（去敏）
     */
    async list(filters = {}) {
        let students = [...this._memoryCache];
        
        // 过滤已删除
        students = students.filter(s => !s.deleted);
        
        // 应用筛选条件
        if (filters.grade) {
            students = students.filter(s => s.grade === filters.grade);
        }
        if (filters.school) {
            students = students.filter(s => s.school === filters.school);
        }
        if (filters.class) {
            students = students.filter(s => s.class === filters.class);
        }
        if (filters.search) {
            const q = filters.search.toLowerCase();
            students = students.filter(s => 
                s.name.toLowerCase().includes(q) ||
                s.no.toLowerCase().includes(q) ||
                s.class.toLowerCase().includes(q)
            );
        }
        
        // 返回去敏版本
        return Anonymizer.sanitize(students);
    },

    /**
     * 根据ID获取学生
     */
    async getById(id) {
        const student = this._memoryCache.find(s => s.id === id);
        if (!student || student.deleted) {return null;}
        return Anonymizer.sanitizeStudent(student);
    },

    /**
     * 根据学号查询（内部使用，返回原始数据）
     */
    async findByNo(no) {
        return this._memoryCache.find(s => s.no === no && !s.deleted);
    },

    /**
     * 获取原始数据（谨慎使用）
     */
    async getRawById(id) {
        return this._memoryCache.find(s => s.id === id && !s.deleted);
    },

    /**
     * 更新学生
     */
    async update(id, changes) {
        const idx = this._memoryCache.findIndex(s => s.id === id);
        if (idx === -1) {throw new Error('学生不存在');}
        
        // 更新数据
        this._memoryCache[idx] = {
            ...this._memoryCache[idx],
            ...changes,
            updatedAt: Date.now()
        };
        
        // 同步到 IndexedDB
        if (db) {
            await db.students.update(id, this._memoryCache[idx]);
            await db.syncQueue.add({
                action: 'update',
                tableName: 'students',
                data: { id, changes },
                timestamp: Date.now(),
                retryCount: 0
            });
        }
        
        return Anonymizer.sanitizeStudent(this._memoryCache[idx]);
    },

    /**
     * 软删除学生
     */
    async delete(id) {
        const idx = this._memoryCache.findIndex(s => s.id === id);
        if (idx === -1) {throw new Error('学生不存在');}
        
        this._memoryCache[idx].deleted = true;
        this._memoryCache[idx].deletedAt = Date.now();
        this._memoryCache[idx].updatedAt = Date.now();
        
        if (db) {
            await db.students.update(id, this._memoryCache[idx]);
            await db.syncQueue.add({
                action: 'delete',
                tableName: 'students',
                data: { id },
                timestamp: Date.now(),
                retryCount: 0
            });
        }
        
        return true;
    },

    /**
     * 从外部数据源批量导入
     */
    async importFromArray(studentsArray) {
        const results = { success: [], errors: [] };
        
        for (const data of studentsArray) {
            try {
                const student = await this.create(data);
                results.success.push(student.displayName);
            } catch (err) {
                results.errors.push({ name: data.name || data.no, reason: err.message });
            }
        }
        
        return results;
    },

    /**
     * 获取统计数据
     */
    async getStats() {
        const students = this._memoryCache.filter(s => !s.deleted);
        return {
            total: students.length,
            byGrade: {
                primary: students.filter(s => s.grade === '小学').length,
                middle: students.filter(s => s.grade === '初中').length,
                high: students.filter(s => s.grade === '高中').length
            },
            withAllergy: students.filter(s => s.allergy && s.allergy.length > 0).length,
            pendingFitness: students.filter(s => !s.fitness || s.fitness.items.every(i => i.s === 'fair')).length
        };
    },

    /**
     * 导出所有数据（用于备份）
     */
    async export() {
        return this._memoryCache.filter(s => !s.deleted);
    },

    /**
     * 清空数据（谨慎使用）
     */
    async clear() {
        this._memoryCache = [];
        if (db) {
            await db.students.clear();
            await db.syncQueue.clear();
        }
    }
};

// ══════════════════════════════════════════════════════
//  6. API 层封装（模拟后端接口）
// ══════════════════════════════════════════════════════
const StudentAPI = {
    /**
     * 获取学生列表（API格式，去敏）
     * GET /api/students
     */
    async getStudents(params = {}) {
        const { grade, school, search, page = 1, pageSize = 50 } = params;
        
        const filters = {};
        if (grade) {filters.grade = grade;}
        if (school) {filters.school = school;}
        if (search) {filters.search = search;}
        
        const students = await StudentService.list(filters);
        
        // 分页
        const start = (page - 1) * pageSize;
        const end = start + pageSize;
        const paginated = students.slice(start, end);
        
        return {
            code: 200,
            data: {
                list: paginated,
                total: students.length,
                page,
                pageSize
            },
            message: 'success'
        };
    },

    /**
     * 获取学生详情（API格式，去敏）
     * GET /api/students/:id
     */
    async getStudentDetail(id) {
        const student = await StudentService.getById(id);
        if (!student) {
            return { code: 404, message: '学生不存在', data: null };
        }
        return { code: 200, data: student, message: 'success' };
    },

    /**
     * 创建学生（API格式）
     * POST /api/students
     */
    async createStudent(data) {
        try {
            const student = await StudentService.create(data);
            return { code: 201, data: student, message: '创建成功' };
        } catch (err) {
            return { code: 400, message: err.message, data: null };
        }
    },

    /**
     * 更新学生（API格式）
     * PUT /api/students/:id
     */
    async updateStudent(id, data) {
        try {
            const student = await StudentService.update(id, data);
            return { code: 200, data: student, message: '更新成功' };
        } catch (err) {
            return { code: 400, message: err.message, data: null };
        }
    },

    /**
     * 删除学生（API格式）
     * DELETE /api/students/:id
     */
    async deleteStudent(id) {
        try {
            await StudentService.delete(id);
            return { code: 200, message: '删除成功', data: null };
        } catch (err) {
            return { code: 400, message: err.message, data: null };
        }
    },

    /**
     * 获取统计数据（API格式）
     * GET /api/students/stats
     */
    async getStats() {
        const stats = await StudentService.getStats();
        return { code: 200, data: stats, message: 'success' };
    }
};

// ══════════════════════════════════════════════════════
//  7. 导出
// ══════════════════════════════════════════════════════
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { StudentService, StudentAPI, Anonymizer, StudentConfig };
} else if (typeof window !== 'undefined') {
    window.StudentService = StudentService;
    window.StudentAPI = StudentAPI;
    window.Anonymizer = Anonymizer;
    window.StudentConfig = StudentConfig;
}
