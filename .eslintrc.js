/**
 * ESLint 配置文件
 * 规范代码风格，避免浏览器兼容性问题
 */
module.exports = {
    env: {
        browser: true,
        es2020: true,
        node: false
    },
    extends: ['eslint:recommended'],
    parserOptions: {
        ecmaVersion: 2020,
        sourceType: 'script' // 当前项目使用传统脚本
    },
    rules: {
        // 错误预防
        'no-unused-vars': ['warn', { 'vars': 'all', 'args': 'after-used' }],
        'no-undef': 'error',
        'no-console': ['warn', { allow: ['error', 'warn', 'log'] }],
        
        // 浏览器兼容性规则
        'no-restricted-syntax': [
            'error',
            {
                selector: 'ChainExpression', // 禁止 optional chaining ?.
                message: 'Optional chaining (?.) 不被 Safari 13 及以下支持，请使用传统写法'
            },
            {
                selector: 'LogicalExpression[operator="??"]', // 禁止 nullish coalescing
                message: 'Nullish coalescing (??) 不被 Safari 13 及以下支持，请使用 ||'
            }
        ],
        
        // 代码风格
        'indent': ['error', 4, { 'SwitchCase': 1 }],
        'quotes': ['error', 'single', { 'avoidEscape': true }],
        'semi': ['error', 'always'],
        'comma-dangle': ['error', 'never'],
        
        // 最佳实践
        'eqeqeq': ['error', 'always'],
        'curly': ['error', 'all'],
        'no-var': 'off', // 允许使用 var（当前代码风格）
        'prefer-const': 'warn',
        
        // 函数规范
        'func-names': ['warn', 'as-needed'],
        'max-lines-per-function': ['warn', { max: 50, skipBlankLines: true, skipComments: true }],
        
        // 变量声明
        'vars-on-top': 'warn',
        'no-use-before-define': ['error', { 'functions': false, 'classes': false }]
    },
    
    // 全局变量声明
    globals: {
        // 项目全局变量
        'STUDENTS': 'writable',
        'REAL_DATA': 'writable',
        'DATA_LOADED': 'writable',
        'gradeFilter': 'writable',
        'currentStudentId': 'writable',
        
        // 第三方库
        'Dexie': 'readonly',
        
        // 项目模块
        'Store': 'readonly',
        'StudentModule': 'readonly',
        'DashboardModule': 'readonly',
        'CanteenModule': 'readonly',
        'AwardsModule': 'readonly',
        'ResourceModule': 'readonly',
        'Anonymizer': 'readonly',
        'StudentService': 'readonly',
        'Toast': 'readonly'
    },
    
    // 忽略文件
    ignorePatterns: [
        'node_modules/',
        'dist/',
        '*.min.js',
        'menu_data.js' // 自动生成的数据文件
    ]
};
