/**
 * Store - 全局状态管理
 * 唯一数据源，所有模块通过订阅模式获取/修改状态
 */
const Store = (function() {
    'use strict';
    
    // 初始状态
    const _state = {
        // 数据
        students: [],
        currentStudent: null,
        currentView: 'dashboard',
        
        // UI 状态
        filters: {
            grade: 'all',
            search: ''
        },
        
        // 加载状态
        dataLoaded: false,
        loading: false,
        
        // 其他数据
        awards: [],
        clubs: [],
        menus: {},
        fitnessHistory: []
    };
    
    // 订阅者列表
    const _listeners = new Map();
    
    /**
     * 获取状态（只读）
     * @param {string} key - 状态键名
     * @returns {*} 状态值
     */
    function get(key) {
        if (key === undefined) {
            // 返回深拷贝，防止外部修改
            return JSON.parse(JSON.stringify(_state));
        }
        return _state[key];
    }
    
    /**
     * 修改状态
     * @param {string} key - 状态键名
     * @param {*} value - 新值
     */
    function set(key, value) {
        const oldValue = _state[key];
        _state[key] = value;
        _notify(key, value, oldValue);
    }
    
    /**
     * 批量修改状态
     * @param {Object} updates - 键值对
     */
    function setMany(updates) {
        Object.entries(updates).forEach(([key, value]) => {
            set(key, value);
        });
    }
    
    /**
     * 订阅状态变更
     * @param {string} key - 状态键名（或 'all' 订阅所有变更）
     * @param {Function} callback - 回调函数 (newValue, oldValue, key) => void
     * @returns {Function} 取消订阅函数
     */
    function subscribe(key, callback) {
        if (!_listeners.has(key)) {
            _listeners.set(key, new Set());
        }
        _listeners.get(key).add(callback);
        
        // 立即调用一次，获取初始值
        if (key !== 'all') {
            callback(_state[key], undefined, key);
        }
        
        // 返回取消订阅函数
        return function unsubscribe() {
            const callbacks = _listeners.get(key);
            if (callbacks) {
                callbacks.delete(callback);
            }
        };
    }
    
    /**
     * 通知订阅者
     */
    function _notify(key, newValue, oldValue) {
        // 通知特定 key 的订阅者
        const specificListeners = _listeners.get(key);
        if (specificListeners) {
            specificListeners.forEach(cb => {
                try {
                    cb(newValue, oldValue, key);
                } catch (err) {
                    console.error(`[Store] 订阅者执行失败 (${key}):`, err);
                }
            });
        }
        
        // 通知 'all' 订阅者
        const allListeners = _listeners.get('all');
        if (allListeners) {
            allListeners.forEach(cb => {
                try {
                    cb({ key, newValue, oldValue }, undefined, 'all');
                } catch (err) {
                    console.error('[Store] all 订阅者执行失败:', err);
                }
            });
        }
    }
    
    /**
     * 获取当前视图
     */
    function getCurrentView() {
        return _state.currentView;
    }
    
    /**
     * 切换视图
     * @param {string} viewId - 视图 ID
     */
    function switchView(viewId) {
        if (_state.currentView === viewId) {return;}
        set('currentView', viewId);
    }
    
    /**
     * 获取当前学生
     */
    function getCurrentStudent() {
        return _state.currentStudent;
    }
    
    /**
     * 设置当前学生
     * @param {Object|string} student - 学生对象或 ID
     */
    function setCurrentStudent(student) {
        if (typeof student === 'string') {
            // 通过 ID 查找
            student = _state.students.find(s => s.id === student);
        }
        set('currentStudent', student);
    }
    
    /**
     * 获取学生列表
     */
    function getStudents() {
        return _state.students;
    }
    
    /**
     * 设置学生列表
     * @param {Array} students - 学生数组
     */
    function setStudents(students) {
        set('students', students);
        set('dataLoaded', true);
    }
    
    /**
     * 根据 ID 查找学生
     * @param {string} id - 学生 ID
     */
    function findStudentById(id) {
        return _state.students.find(s => s.id === id);
    }
    
    /**
     * 更新筛选器
     * @param {Object} filters - 筛选条件
     */
    function updateFilters(filters) {
        set('filters', { ..._state.filters, ...filters });
    }
    
    /**
     * 重置状态（调试用）
     */
    function reset() {
        Object.keys(_state).forEach(key => {
            if (Array.isArray(_state[key])) {
                _state[key] = [];
            } else if (typeof _state[key] === 'object' && _state[key] !== null) {
                _state[key] = {};
            } else if (typeof _state[key] === 'boolean') {
                _state[key] = false;
            } else {
                _state[key] = null;
            }
        });
        _listeners.clear();
        console.log('[Store] 状态已重置');
    }
    
    // 公共 API
    return {
        get,
        set,
        setMany,
        subscribe,
        
        // 便捷方法
        getCurrentView,
        switchView,
        getCurrentStudent,
        setCurrentStudent,
        getStudents,
        setStudents,
        findStudentById,
        updateFilters,
        reset
    };
})();

console.log('[Store] 状态管理模块加载完成');
