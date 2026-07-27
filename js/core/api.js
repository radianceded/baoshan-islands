/**
 * API 模块 - AI 相关工具和数据调用
 * 包含百度千帆API调用、AI提示管理、响应解析
 */
const Api = (function() {
    'use strict';

    // ══════════════════════════════════════════════════════
    //  百度千帆 API 配置
    // ══════════════════════════════════════════════════════
    const AI_CONFIG = {
        provider: 'baidu',  // 可选: baidu, siliconflow, mock
        baidu: {
            apiKey: ''  // key 已移至服务端，不再硬编码,
            baseUrl: 'https://qianfan.baidubce.com/v2',
            model: 'ernie-5.0-thinking-preview-8k'
        },
        siliconflow: {
            apiKey: 'YOUR_API_KEY_HERE',
            baseUrl: 'https://api.siliconflow.cn/v1',
            model: 'Qwen/Qwen2.5-7B-Instruct'
        },
        useMockData: false  // 调试时可设为true，使用预设数据
    };

    // ══════════════════════════════════════════════════════
    //  AI Prompt 配置（4个模块）
    // ══════════════════════════════════════════════════════
    const AI_PROMPTS = {
        fitness: {
            name: '体质健康顾问',
            systemPrompt: '你是一位专业的校园体育与健康管理顾问。你的任务是根据学生的体测数据、过敏原、健康档案等信息，提供个性化、科学的健康成长建议。注意语言要亲切、专业、简洁。注意：学生姓名已脱敏处理（如"张**"），请直接使用该名称。',
            userPromptTemplate: (student) => `请为以下学生生成体质健康建议：

学生ID：${student.id}
去敏姓名：${student.displayName || student.name}
年级：${student.grade}
性别：${student.sex}
年龄：${student.age}岁

体测数据：
${student.fitness.items.map(i => `- ${i.n}：${i.e} (${i.s === 'great' ? '优秀' : i.s === 'good' ? '良好' : i.s === 'fair' ? '一般' : '待提升'})`).join('\n')}

健康档案备注：${student.special || '无'}
过敏原：${student.allergy.join('、') || '无'}
饮食注意：${student.diet_note || '无'}
兴趣偏好：${student.interests.join('、')}

请从以下角度生成建议：
1. 整体状况评价
2. 重点关注事项
3. 运动建议（结合兴趣）
4. 日常健康提示

请用JSON格式返回，格式如下：
{"整体状况":"...","重点关注":"...","运动建议":"...","日常提示":"..."}`
        },
        canteen: {
            name: '智慧食堂推餐',
            systemPrompt: '你是一位专业的校园营养师。你的任务是根据学生的体质、健康状况、过敏原等信息，推荐合适的校园餐食，并解释推荐理由。注意考虑饮食禁忌和营养均衡。注意：学生姓名已脱敏处理（如"张**"），请直接使用该名称。',
            userPromptTemplate: (student) => `请为以下学生推荐午餐和晚餐方案：

学生ID：${student.id}
去敏姓名：${student.displayName || student.name}
年级：${student.grade}
年龄：${student.age}岁

过敏原（必须完全规避）：${student.allergy.join('、') || '无'}
饮食医嘱：${student.diet_note || '无'}
健康备注：${student.special || '无'}
体能薄弱项：${student.fitness.items.filter(i => i.s === 'fair' || i.s === 'watch').map(i => i.n).join('、') || '无'}

请根据学生的健康状况，推荐：
1. 午餐选择（A餐或B餐）及推荐理由
2. 晚餐菜品建议（3-4道）及营养说明
3. 是否需要额外注意的事项

请用JSON格式返回，格式如下：
{"午餐推荐":"A或B","午餐理由":"...","晚餐菜品":[{"菜名":"...","理由":"..."},...],"注意事项":"..."}`
        },
        activity: {
            name: '课外活动匹配',
            systemPrompt: '你是一位专业的青少年活动规划师。你的任务是根据学生的兴趣、体能特点、年级等，推荐合适的课外活动或社团，并说明推荐理由。注意：学生姓名已脱敏处理（如"张**"），请直接使用该名称。',
            userPromptTemplate: (student) => `请为以下学生推荐课外活动：

学生ID：${student.id}
去敏姓名：${student.displayName || student.name}
年级：${student.grade}
性别：${student.sex}
年龄：${student.age}岁

兴趣爱好：${student.interests.join('、')}
体能优势：${student.fitness.items.filter(i => i.s === 'good' || i.s === 'great').map(i => i.n).join('、') || '待评估'}
体能注意：${student.special || '无'}
健康状况：${student.diet_note || '良好'}

请推荐2-3个适合的课外活动或社团，说明：
1. 活动名称
2. 推荐理由（如何匹配学生特点）
3. 适合的参与时间

请用JSON格式返回，格式如下：
{"活动":[{"名称":"...","理由":"...","时间":"..."},...],"备注":"..."}`
        },
        reading: {
            name: '阅读资源推荐',
            systemPrompt: '你是一位专业的校园阅读推广人。你的任务是根据学生的借阅历史、兴趣偏好，推荐合适的图书，帮助学生拓展阅读视野。注意：学生姓名已脱敏处理（如"张**"），请直接使用该名称。',
            userPromptTemplate: (student) => `请为以下学生推荐图书：

学生ID：${student.id}
去敏姓名：${student.displayName || student.name}
年级：${student.grade}
年龄：${student.age}岁

兴趣爱好：${student.interests.join('、')}

借阅历史：
${student.books.map(b => `- 《${b.t}》by ${b.a} (${b.s})`).join('\n')}

请基于学生的兴趣和借阅历史，推荐3-4本适合的图书：
1. 书名
2. 作者
3. 推荐理由（为什么适合这个学生）

请用JSON格式返回，格式如下：
{"推荐":[{"书名":"...","作者":"...","理由":"..."},...],"阅读建议":"..."}`
        }
    };

    // ══════════════════════════════════════════════════════
    //  API 调用函数
    // ══════════════════════════════════════════════════════

    /**
     * 调用百度千帆API
     * @param {Object} prompt - 提示配置 {systemPrompt, userPrompt}
     * @param {Object} config - API配置
     * @returns {Promise<string>} AI响应文本
     */
    async function callBaiduAPI(prompt, config = AI_CONFIG.baidu) {
        const url = `${config.baseUrl}/chat/completions`;
        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${config.apiKey}`
        };
        const body = {
            model: config.model,
            messages: [
                { role: 'system', content: prompt.systemPrompt },
                { role: 'user', content: prompt.userPrompt }
            ],
            temperature: 0.7,
            max_tokens: 2000
        };

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                throw new Error(`API错误: ${response.status}`);
            }

            const data = await response.json();
            return data.choices[0].message.content;
        } catch (error) {
            console.error('API调用失败:', error);
            throw error;
        }
    }

    /**
     * 调用 SiliconFlow API
     * @param {Object} prompt - 提示配置
     * @returns {Promise<string>} AI响应文本
     */
    async function callSiliconFlowAPI(prompt) {
        const config = AI_CONFIG.siliconflow;
        const url = `${config.baseUrl}/chat/completions`;
        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${config.apiKey}`
        };
        const body = {
            model: config.model,
            messages: [
                { role: 'system', content: prompt.systemPrompt },
                { role: 'user', content: prompt.userPrompt }
            ],
            temperature: 0.7,
            max_tokens: 2000
        };

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: headers,
                body: JSON.stringify(body)
            });

            if (!response.ok) {
                throw new Error(`API错误: ${response.status}`);
            }

            const data = await response.json();
            return data.choices[0].message.content;
        } catch (error) {
            console.error('SiliconFlow API调用失败:', error);
            throw error;
        }
    }

    /**
     * 通用AI调用函数
     * @param {string} promptType - AI模块类型: fitness, canteen, activity, reading
     * @param {Object} student - 学生对象
     * @returns {Promise<string|null>} AI响应文本
     */
    async function callAI(promptType, student) {
        if (AI_CONFIG.useMockData) {
            return null; // 使用预设数据
        }

        const prompt = AI_PROMPTS[promptType];
        if (!prompt) {
            console.error('未知的AI模块:', promptType);
            return null;
        }

        // 构建用户提示
        prompt.userPrompt = prompt.userPromptTemplate(student);

        try {
            if (AI_CONFIG.provider === 'baidu') {
                return await callBaiduAPI(prompt, AI_CONFIG.baidu);
            } else if (AI_CONFIG.provider === 'siliconflow') {
                return await callSiliconFlowAPI(prompt);
            }
        } catch (error) {
            console.error('AI调用失败:', error);
            return null;
        }

        return null;
    }

    /**
     * 解析AI响应（旧版兼容）
     * @param {string} type - 响应类型
     * @param {string} text - 响应文本
     * @param {Object} student - 学生对象
     * @returns {Object|null} 解析后的数据
     */
    function parseAIResponse(type, text, student) {
        try {
            // 尝试提取JSON
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                return JSON.parse(jsonMatch[0]);
            }
        } catch (e) {
            console.error('解析AI响应失败:', e);
        }
        return null;
    }

    /**
     * 解析AI返回的JSON响应（新版）
     * @param {string} type - 响应类型
     * @param {string} text - 响应文本
     * @returns {Object|null} 解析后的数据
     */
    function parseAIResponseText(type, text) {
        try {
            // 尝试提取JSON部分
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                return JSON.parse(jsonMatch[0]);
            }
        } catch (e) {
            console.error('解析AI响应失败:', e);
        }
        return null;
    }

    /**
     * 获取AI Prompt用标识（使用ID而非姓名）
     * @param {Object} student - 学生对象
     * @returns {string} 标识字符串
     */
    function getAIPromptIdentifier(student) {
        if (!student) {return '';}
        return `学生ID:${student.id}`;
    }

    /**
     * 获取AI配置
     * @returns {Object} 当前AI配置
     */
    function getConfig() {
        return { ...AI_CONFIG };
    }

    /**
     * 设置AI提供商
     * @param {string} provider - 提供商名称: baidu, siliconflow, mock
     */
    function setProvider(provider) {
        if (['baidu', 'siliconflow', 'mock'].includes(provider)) {
            AI_CONFIG.provider = provider;
            console.log('[Api] AI提供商已切换为:', provider);
        }
    }

    /**
     * 切换Mock数据模式
     * @param {boolean} enabled - 是否启用
     */
    function setMockData(enabled) {
        AI_CONFIG.useMockData = enabled;
        console.log('[Api] Mock数据模式:', enabled ? '已启用' : '已禁用');
    }

    /**
     * 更新API密钥
     * @param {string} provider - 提供商
     * @param {string} apiKey - 新密钥
     */
    function setApiKey(provider, apiKey) {
        if (AI_CONFIG[provider]) {
            AI_CONFIG[provider].apiKey = apiKey;
        }
    }

    // 公共 API
    return {
        callBaiduAPI,
        callSiliconFlowAPI,
        callAI,
        parseAIResponse,
        parseAIResponseText,
        getAIPromptIdentifier,
        getConfig,
        setProvider,
        setMockData,
        setApiKey,
        AI_PROMPTS
    };
})();

console.log('[Api] API模块加载完成');
