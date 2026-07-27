// ══════════════════════════════════════════════════════
//  AI Tools Module - AI 推荐工具模块
// ══════════════════════════════════════════════════════

const AIToolsModule = (function() {
    'use strict';
    
    // ══════════════════════════════════════════════════════
    //  AI 推荐生成器（通用）
    // ══════════════════════════════════════════════════════
    function generate(student, moduleType, outputElId) {
        if (!student) {
            if (typeof toast === 'function') {toast('请先选择学生');}
            return;
        }
        
        var sn = (typeof getDisplayName === 'function') ? getDisplayName(student) : student.name;
        var el = document.getElementById(outputElId);
        if (!el) {return;}
        
        // 显示加载状态
        var aiStatusEl = el.parentElement.querySelector('.ai-status');
        if (aiStatusEl) {
            aiStatusEl.className = 'ai-status loading';
            aiStatusEl.innerHTML = '<span class="ai-status-dot"></span>AI 生成中...';
        }
        
        // 根据模块类型生成内容
        var blocks = _generateBlocks(student, sn, moduleType);
        
        // 模拟AI延迟
        setTimeout(function() {
            // 更新状态
            if (aiStatusEl) {
                aiStatusEl.className = 'ai-status done';
                aiStatusEl.innerHTML = '<span class="ai-status-dot"></span>生成完成';
            }
            
            // 渲染结果
            el.innerHTML = blocks.map(function(b) {
                return '<div class="ai-block">'
                    + '<div class="ai-block-label"><span class="ai-block-dot" style="background:var(--' + b.color + ')"></span>' + b.label + '</div>'
                    + '<div class="ai-text ' + b.color + '">' + b.text + '</div>'
                    + '</div>';
            }).join('')
            + '<div class="ai-disclaimer"><span>⚠️</span>以上内容由 AI 辅助生成，仅供参考，请结合实际情况审慎使用。</div>';
            
            el.classList.add('visible');
            if (typeof toast === 'function') {toast('✓ ' + sn + ' 的 AI 建议已生成');}
        }, 1200);
    }
    
    // ══════════════════════════════════════════════════════
    //  生成AI内容块
    // ══════════════════════════════════════════════════════
    function _generateBlocks(student, sn, moduleType) {
        var blocks = [];
        
        switch (moduleType) {
            case 'fitness':
                blocks = _generateFitnessBlocks(student, sn);
                break;
            case 'canteen':
                blocks = _generateCanteenBlocks(student, sn);
                break;
            case 'activity':
                blocks = _generateActivityBlocks(student, sn);
                break;
            case 'reading':
                blocks = _generateReadingBlocks(student, sn);
                break;
            default:
                blocks = _generateGeneralBlocks(student, sn);
        }
        
        return blocks;
    }
    
    // ══════════════════════════════════════════════════════
    //  体质健康分析 - 优化版：提供具体每日运动量和务实建议
    // ══════════════════════════════════════════════════════
    function _generateFitnessBlocks(student, sn) {
        var fitness = student.fitness || { items: [] };
        var items = fitness.items || [];
        var age = student.age || 10;
        
        var goodCount = items.filter(function(i) { return i.s === 'good' || i.s === 'great'; }).length;
        var weakItems = items.filter(function(i) { return i.s === 'watch' || i.s === 'fair'; });
        var weakNames = weakItems.map(function(i) { return i.n; });
        
        var blocks = [];
        
        // 1. 整体状况评估
        if (goodCount >= items.length * 0.7) {
            blocks.push({ label: '整体状况', color: 'green', text: sn + '的体测表现良好，多个项目达到优秀水平。建议保持当前运动强度，每日中等强度运动30-40分钟即可。' });
        } else if (goodCount >= items.length * 0.4) {
            blocks.push({ label: '整体状况', color: 'amber', text: sn + '的体测表现中等，部分项目有提升空间。建议每日安排40-50分钟运动，循序渐进提升体能。' });
        } else {
            blocks.push({ label: '整体状况', color: 'amber', text: sn + '的体测多项指标需要加强。建议从低强度开始，每日30分钟，逐步增加到50分钟，避免运动损伤。' });
        }
        
        // 2. 薄弱项目针对性训练（具体化）
        if (weakItems.length > 0) {
            var weakText = weakItems.map(function(i) { return i.n + '(' + _statusLabel(i.s) + ')'; }).join('、');
            var exercisePlan = _generateSpecificExercisePlan(weakNames, age, sn);
            blocks.push({
                label: '薄弱项目提升方案',
                color: 'blue',
                text: '需重点提升：' + weakText + '。' + exercisePlan
            });
        }
        
        // 3. 每日运动量建议（结合小学生体力特点）
        var dailyPlan = _generateDailyExercisePlan(weakNames, age, student.interests || []);
        blocks.push({
            label: '每日运动安排',
            color: 'green',
            text: dailyPlan
        });
        
        // 4. 基于兴趣的运动建议
        var interests = student.interests || [];
        if (interests.length > 0) {
            var interestExercise = _generateInterestBasedExercise(interests, weakNames);
            blocks.push({
                label: '兴趣结合建议',
                color: 'purple',
                text: '结合' + sn + '喜欢的' + interests.join('、') + '，推荐：' + interestExercise
            });
        }
        
        // 5. 注意事项
        if (student.special) {
            blocks.push({ label: '特别注意', color: 'red', text: student.special + '。运动前务必充分热身5-10分钟，运动中如出现不适立即停止。' });
        } else {
            blocks.push({ label: '运动安全', color: 'amber', text: '运动前热身5分钟（慢跑、关节活动），运动后拉伸5分钟。避免空腹或饭后立即运动，运动中适量补水。' });
        }
        
        return blocks;
    }
    
    // 生成针对性训练方案
    function _generateSpecificExercisePlan(weakItems, age, sn) {
        var plans = [];
        
        if (weakItems.indexOf('50米跑') >= 0 || weakItems.indexOf('速度') >= 0) {
            plans.push('速度提升：短距离冲刺跑（20米×4组，组间休息60秒），每周3次');
        }
        if (weakItems.indexOf('坐位体前屈') >= 0 || weakItems.indexOf('柔韧性') >= 0) {
            plans.push('柔韧性：坐位体前屈拉伸保持15秒×3组，睡前瑜伽10分钟，每天进行');
        }
        if (weakItems.indexOf('立定跳远') >= 0 || weakItems.indexOf('下肢力量') >= 0) {
            plans.push('下肢力量：蛙跳10次×3组、单脚跳各10次，隔天训练，注意落地缓冲');
        }
        if (weakItems.indexOf('仰卧起坐') >= 0 || weakItems.indexOf('核心力量') >= 0) {
            plans.push('核心力量：仰卧起坐15次×2组、平板支撑20秒×2组，每天可进行');
        }
        if (weakItems.indexOf('跳绳') >= 0 || weakItems.indexOf('协调性') >= 0) {
            plans.push('跳绳协调：单摇跳30秒×3组，逐步增加到1分钟，每天练习');
        }
        if (weakItems.indexOf('肺活量') >= 0 || weakItems.indexOf('耐力') >= 0) {
            plans.push('心肺耐力：慢跑或快走800-1000米，保持能说话的速度，每周3-4次');
        }
        if (weakItems.indexOf('上肢力量') >= 0 || weakItems.indexOf('引体向上') >= 0) {
            plans.push('上肢力量：俯卧撑（可跪姿）8次×2组、悬垂10秒×2组，隔天训练');
        }
        if (weakItems.indexOf('视力') >= 0) {
            plans.push('视力保护：每天户外活动累计1小时以上，课间远眺5分钟，减少连续用眼时间');
        }
        if (weakItems.indexOf('体重管理') >= 0 || weakItems.indexOf('BMI') >= 0) {
            plans.push('体重管理：每天中高强度运动40分钟以上，控制零食，增加蔬菜摄入');
        }
        
        if (plans.length === 0) {
            return '建议每天进行多样化运动：跳绳5分钟、慢跑10分钟、拉伸5分钟。';
        }
        
        return '具体训练：' + plans.join('；') + '。';
    }
    
    // 生成每日运动计划（适合小学生体力）
    function _generateDailyExercisePlan(weakItems, age, interests) {
        var intensity = weakItems.length >= 3 ? '中低' : (weakItems.length >= 1 ? '中等' : '中等偏高');
        var duration = weakItems.length >= 3 ? '40分钟' : (weakItems.length >= 1 ? '45-50分钟' : '50-60分钟');
        
        var schedule = '【' + intensity + '强度，每日' + duration + '】\n';
        schedule += '早晨（10分钟）：广播操或拉伸，唤醒身体\n';
        schedule += '课间（累计15分钟）：跳绳、踢毽子、走廊快走，每节课后活动3-5分钟\n';
        schedule += '放学后（25-35分钟）：';
        
        if (interests.indexOf('篮球') >= 0 || interests.indexOf('足球') >= 0 || interests.indexOf('排球') >= 0) {
            schedule += '球类活动20分钟 + 针对性训练10分钟';
        } else if (interests.indexOf('跑步') >= 0 || interests.indexOf('田径') >= 0) {
            schedule += '慢跑或变速跑20分钟 + 拉伸放松10分钟';
        } else if (interests.indexOf('舞蹈') >= 0 || interests.indexOf('体操') >= 0) {
            schedule += '舞蹈或韵律操25分钟 + 柔韧性练习10分钟';
        } else if (interests.indexOf('游泳') >= 0) {
            schedule += '有条件的可进行游泳30分钟，或替换为跳绳+慢跑';
        } else {
            schedule += '跳绳5分钟 + 慢跑或快走15分钟 + 游戏类活动10分钟';
        }
        
        schedule += '\n周末：增加户外活动1-2小时（骑行、爬山、球类等）';
        
        return schedule;
    }
    
    // 基于兴趣生成运动建议
    function _generateInterestBasedExercise(interests, weakItems) {
        var suggestions = [];
        
        for (var i = 0; i < interests.length; i++) {
            var interest = interests[i];
            if (interest === '篮球') {
                suggestions.push('篮球：运球练习10分钟可提升协调性，投篮练习锻炼上肢力量');
            } else if (interest === '足球') {
                suggestions.push('足球：带球跑动锻炼耐力和下肢力量，适合提升肺活量');
            } else if (interest === '羽毛球' || interest === '乒乓球') {
                suggestions.push(interest + '：快速移动锻炼反应速度和下肢力量，挥拍动作锻炼上肢');
            } else if (interest === '游泳') {
                suggestions.push('游泳：全身性运动，对心肺功能和肌肉力量都有很好提升');
            } else if (interest === '跑步') {
                suggestions.push('跑步：建议采用间歇跑，快慢交替，提升心肺更有效');
            } else if (interest === '舞蹈') {
                suggestions.push('舞蹈：提升柔韧性和协调性，同时锻炼核心力量');
            } else if (interest === '武术' || interest === '跆拳道') {
                suggestions.push(interest + '：提升柔韧性、平衡感和下肢力量');
            } else if (interest === '骑行') {
                suggestions.push('骑行：锻炼下肢力量和心肺耐力，建议每次30分钟以上');
            } else if (interest === '跳绳') {
                suggestions.push('跳绳：每天3组，每组1分钟，逐步提升速度和连续性');
            }
        }
        
        if (suggestions.length === 0) {
            return '尝试多样化的体育活动，找到喜欢的运动方式更容易坚持。';
        }
        
        return suggestions.join('；') + '。将兴趣与薄弱项目结合，事半功倍。';
    }
    
    // ══════════════════════════════════════════════════════
    //  推餐推荐 - 优化版：提供具体营养搭配和每日摄入量
    // ══════════════════════════════════════════════════════
    function _generateCanteenBlocks(student, sn) {
        var allergy = student.allergy || [];
        var age = student.age || 10;
        var fitnessItems = student.fitness && student.fitness.items ? student.fitness.items : [];
        var weakItems = fitnessItems.filter(function(i) { return i.s === 'watch' || i.s === 'fair'; });
        var weakNames = weakItems.map(function(i) { return i.n; });
        var blocks = [];
        
        // 1. 过敏提醒
        if (allergy.length > 0) {
            blocks.push({ label: '过敏提醒', color: 'amber', text: sn + ' 对以下食物过敏：' + allergy.join('、') + '。推荐餐品已自动规避含有相关食材的菜品。' });
        }
        
        // 2. 营养需求分析（基于体测数据）
        var focus = [];
        if (weakNames.indexOf('身高') >= 0 || weakNames.indexOf('体重') >= 0 || weakNames.indexOf('BMI') >= 0) {
            focus.push('钙质、蛋白质（促进骨骼发育）');
        }
        if (weakNames.indexOf('肺活量') >= 0 || weakNames.indexOf('耐力') >= 0) {
            focus.push('铁质、优质蛋白（提升血液携氧能力）');
        }
        if (weakNames.indexOf('视力') >= 0) {
            focus.push('维生素A、叶黄素（保护视力）');
        }
        if (weakNames.indexOf('力量') >= 0 || weakNames.indexOf('跳远') >= 0) {
            focus.push('蛋白质、钙质（增强肌肉力量）');
        }
        
        if (focus.length > 0) {
            blocks.push({ label: '营养需求分析', color: 'blue', text: '基于体测结果，' + sn + ' 需要重点补充：' + focus.join('、') + '。' });
        }
        
        // 3. 每日热量需求
        var calorieNeeds = age <= 8 ? 1400 : (age <= 10 ? 1600 : (age <= 12 ? 1800 : 2000));
        blocks.push({ 
            label: '每日营养摄入建议', 
            color: 'green', 
            text: sn + '（' + age + '岁）每日建议摄入：热量约' + calorieNeeds + 'kcal，蛋白质' + (age <= 8 ? 35 : (age <= 10 ? 40 : 50)) + 'g。三餐分配：早餐30%、午餐40%、晚餐30%。午餐建议摄入约' + Math.round(calorieNeeds * 0.4) + 'kcal。' 
        });
        
        // 4. 午餐推荐
        blocks.push({ 
            label: '今日午餐推荐', 
            color: 'teal', 
            text: '推荐选择营养均衡的套餐，包含：优质蛋白（鱼/肉/蛋）约100-120g、主食（米饭/面食）约150-200g、蔬菜约150g、水果1份。避免油炸食品，多选择蒸煮炖类菜品。' 
        });
        
        // 5. 晚餐建议
        blocks.push({ 
            label: '晚餐搭配建议', 
            color: 'purple', 
            text: '晚餐建议清淡为主：清蒸鱼/瘦肉80-100g、时令蔬菜200g、杂粮饭/红薯100-150g、豆腐汤1碗。晚餐热量约占全天30%，约' + Math.round(calorieNeeds * 0.3) + 'kcal。睡前2小时避免进食。' 
        });
        
        // 6. 健康饮食习惯
        blocks.push({ 
            label: '健康饮食习惯', 
            color: 'amber', 
            text: '1. 细嚼慢咽，每餐用时15-20分钟；2. 不挑食、不偏食，每天摄入12种以上食物；3. 少喝含糖饮料，多喝白开水（每日800-1200ml）；4. 控制零食，优先选择水果、坚果、酸奶。' 
        });
        
        return blocks;
    }
    
    // ══════════════════════════════════════════════════════
    //  课外活动推荐 - 优化版：提供具体活动安排和时间规划
    // ══════════════════════════════════════════════════════
    function _generateActivityBlocks(student, sn) {
        var interests = student.interests || [];
        var fitnessItems = student.fitness && student.fitness.items ? student.fitness.items : [];
        var age = student.age || 10;
        var blocks = [];
        
        // 分析体能状况
        var weakItems = fitnessItems.filter(function(i) { return i.s === 'watch' || i.s === 'fair'; });
        var goodItems = fitnessItems.filter(function(i) { return i.s === 'good' || i.s === 'great'; });
        var weakNames = weakItems.map(function(i) { return i.n; });
        var goodNames = goodItems.map(function(i) { return i.n; });
        
        // 1. 兴趣与体能分析
        var interestText = interests.length > 0 ? interests.join('、') : '暂无记录';
        var fitnessText = goodNames.length > 0 ? '体能优势：' + goodNames.join('、') : '体能状况待提升';
        blocks.push({ 
            label: '兴趣与体能分析', 
            color: 'blue', 
            text: sn + ' 的兴趣爱好：' + interestText + '。' + fitnessText + (weakNames.length > 0 ? '；待提升项目：' + weakNames.join('、') : '') + '。以下推荐基于兴趣匹配和体能改善双重目标。' 
        });
        
        // 2. 个性化活动推荐
        var activitySuggestions = [];
        if (interests.indexOf('音乐') >= 0) activitySuggestions.push('合唱团（每周二、四下午，低强度）');
        if (interests.indexOf('绘画') >= 0) activitySuggestions.push('美术社团（每周二、五下午，低强度）');
        if (interests.indexOf('足球') >= 0) activitySuggestions.push('足球社团（每周一、三、五下午，高强度）');
        if (interests.indexOf('篮球') >= 0) activitySuggestions.push('篮球社团（每周二、四下午，高强度）');
        if (interests.indexOf('编程') >= 0) activitySuggestions.push('编程社团（每周三下午，低强度）');
        if (interests.indexOf('舞蹈') >= 0) activitySuggestions.push('舞蹈社团（每周一、三下午，中强度）');
        if (interests.indexOf('科学') >= 0) activitySuggestions.push('科学实验社（每周二下午，低强度）');
        if (interests.indexOf('阅读') >= 0) activitySuggestions.push('阅读俱乐部（每周一、三中午，低强度）');
        
        // 根据薄弱项添加改善性活动
        if (weakNames.indexOf('肺活量') >= 0 || weakNames.indexOf('耐力') >= 0) {
            activitySuggestions.push('有氧训练（每周二、四下午，针对性提升心肺功能）');
        }
        if (weakNames.indexOf('柔韧性') >= 0 || weakNames.indexOf('坐位体前屈') >= 0) {
            activitySuggestions.push('瑜伽/拉伸（每周三下午，改善柔韧性）');
        }
        if (weakNames.indexOf('力量') >= 0 || weakNames.indexOf('引体向上') >= 0) {
            activitySuggestions.push('体能训练（每周一、五下午，系统力量训练）');
        }
        
        if (activitySuggestions.length === 0) {
            activitySuggestions.push('阳光体育（每天课间10分钟，保持活力）');
            activitySuggestions.push('兴趣社团（每周选修课，探索兴趣）');
        }
        
        blocks.push({ 
            label: '推荐活动（含时间地点）', 
            color: 'green', 
            text: activitySuggestions.slice(0, 4).join('；') + '。建议根据体能状况选择适合强度的活动，循序渐进提升。' 
        });
        
        // 3. 每周活动规划
        var weeklyHours = age <= 8 ? '3-5小时' : (age <= 10 ? '5-7小时' : '7-10小时');
        blocks.push({ 
            label: '每周活动规划', 
            color: 'teal', 
            text: '建议每周课外活动总时长：' + weeklyHours + '。分配建议：校内社团2-3次（每次1-1.5小时）、课间运动每天累计30分钟、周末户外活动1-2小时。避免过度疲劳，保证充足睡眠。' 
        });
        
        // 4. 体能改善专项建议
        if (weakNames.length > 0) {
            blocks.push({ 
                label: '体能改善专项', 
                color: 'amber', 
                text: '针对' + weakNames.join('、') + '待提升，建议：每周安排2-3次针对性训练，每次20-30分钟；结合兴趣选择活动，提高参与积极性；记录进步情况，建立成就感。' 
            });
        }
        
        // 5. 安全提示
        blocks.push({ 
            label: '活动安全提示', 
            color: 'purple', 
            text: '1. 运动前充分热身5-10分钟；2. 穿着合适的运动服装和鞋子；3. 携带水壶，运动中适量补水；4. 如感到不适立即停止并告知老师；5. 运动后做拉伸放松。' 
        });
        
        return blocks;
    }
    
    // ══════════════════════════════════════════════════════
    //  阅读推荐 - 优化版：提供具体书单和阅读计划
    // ══════════════════════════════════════════════════════
    function _generateReadingBlocks(student, sn) {
        var books = student.books || [];
        var interests = student.interests || [];
        var age = student.age || 10;
        var grade = student.grade || '小学';
        var blocks = [];
        
        // 1. 阅读历史和兴趣分析
        var bookHistory = books.length > 0 ? books.map(function(b) { return b.t; }).join('、') : '暂无记录';
        var interestText = interests.length > 0 ? interests.join('、') : '综合发展';
        blocks.push({ 
            label: '阅读兴趣分析', 
            color: 'blue', 
            text: sn + '（' + age + '岁）的借阅记录：' + bookHistory + '。兴趣标签：' + interestText + '。以下推荐基于阅读历史和兴趣偏好，兼顾适龄性和阅读难度。' 
        });
        
        // 2. 阅读难度和每日目标
        var readingLevel, dailyTime, pages;
        if (grade.indexOf('一') >= 0 || age <= 7) {
            readingLevel = '初级'; dailyTime = '20-30分钟'; pages = '10-15页';
        } else if (grade.indexOf('二') >= 0 || age <= 8) {
            readingLevel = '初级+'; dailyTime = '25-35分钟'; pages = '15-20页';
        } else if (grade.indexOf('三') >= 0 || age <= 9) {
            readingLevel = '中级'; dailyTime = '30-40分钟'; pages = '20-25页';
        } else if (grade.indexOf('四') >= 0 || age <= 10) {
            readingLevel = '中级+'; dailyTime = '35-45分钟'; pages = '25-30页';
        } else if (grade.indexOf('五') >= 0 || age <= 11) {
            readingLevel = '高级'; dailyTime = '40-50分钟'; pages = '30-40页';
        } else {
            readingLevel = '高级+'; dailyTime = '45-60分钟'; pages = '40-50页';
        }
        
        blocks.push({ 
            label: '阅读难度与目标', 
            color: 'green', 
            text: '建议阅读难度：' + readingLevel + '。每日阅读目标：' + dailyTime + '，约' + pages + '。建议固定阅读时间（如睡前），创造安静的阅读环境。' 
        });
        
        // 3. 个性化书单推荐
        var bookRecommendations = [];
        
        // 根据兴趣推荐
        if (interests.indexOf('音乐') >= 0) bookRecommendations.push('《音乐简史（少儿版）》· 2周 · 中级');
        if (interests.indexOf('绘画') >= 0) bookRecommendations.push('《世界名画赏析（儿童版）》· 3周 · 中级');
        if (interests.indexOf('科学') >= 0) bookRecommendations.push('《十万个为什么（新版）》· 4周 · 初级');
        if (interests.indexOf('历史') >= 0) bookRecommendations.push('《中华上下五千年（少儿版）》· 4周 · 中级');
        if (interests.indexOf('足球') >= 0) bookRecommendations.push('《足球小将》· 2周 · 初级');
        if (interests.indexOf('篮球') >= 0) bookRecommendations.push('《灌篮高手（精选版）》· 3周 · 初级');
        if (interests.indexOf('编程') >= 0) bookRecommendations.push('《Scratch编程趣味卡》· 2周 · 初级');
        if (interests.indexOf('阅读') >= 0) bookRecommendations.push('《夏洛的网》· 2周 · 中级');
        
        // 通用推荐
        var generalBooks = [
            '《窗边的小豆豆》· 2周 · 中级',
            '《小王子》· 2周 · 中级',
            '《草房子》· 2周 · 中级',
            '《爱的教育》· 3周 · 中级'
        ];
        
        while (bookRecommendations.length < 4 && generalBooks.length > 0) {
            bookRecommendations.push(generalBooks.shift());
        }
        
        blocks.push({ 
            label: '个性化书单（含建议用时）', 
            color: 'teal', 
            text: bookRecommendations.slice(0, 4).join('；') + '。以上书目均可在学校图书馆借阅，建议按顺序阅读，每读完一本记录心得。' 
        });
        
        // 4. 阅读计划建议
        blocks.push({ 
            label: '阅读计划建议', 
            color: 'purple', 
            text: '1. 制定月度阅读计划，每月2-3本书；2. 准备阅读笔记本，记录好词好句和心得；3. 读完后与家人/同学分享内容；4. 遇到生字先猜意思再查字典；5. 广泛涉猎不同题材，不局限于单一类型。' 
        });
        
        // 5. 阅读习惯培养
        blocks.push({ 
            label: '阅读习惯培养', 
            color: 'amber', 
            text: '1. 固定阅读时间（睡前30分钟最佳）；2. 创造专属阅读角落；3. 减少电子设备干扰；4. 家长陪伴阅读或讨论书中内容；5. 定期去图书馆选书，保持阅读新鲜感。' 
        });
        
        return blocks;
    }
    
    // ══════════════════════════════════════════════════════
    //  通用推荐
    // ══════════════════════════════════════════════════════
    function _generateGeneralBlocks(student, sn) {
        return [
            { label: '综合分析', color: 'blue', text: '基于 ' + sn + ' 的综合档案数据，AI 正在分析最合适的个性化建议...' }
        ];
    }
    
    // ══════════════════════════════════════════════════════
    //  体测状态标签
    // ══════════════════════════════════════════════════════
    function _statusLabel(status) {
        var map = {
            'great': '优秀',
            'good': '良好',
            'fair': '及格',
            'watch': '待提升'
        };
        return map[status] || status;
    }
    
    // ══════════════════════════════════════════════════════
    //  打字机效果
    // ══════════════════════════════════════════════════════
    function typewriterEffect(el, text, speed) {
        speed = speed || 30;
        el.textContent = '';
        var i = 0;
        var timer = setInterval(function() {
            if (i < text.length) {
                el.textContent += text.charAt(i);
                i++;
            } else {
                clearInterval(timer);
            }
        }, speed);
    }
    
    // ══════════════════════════════════════════════════════
    //  构建 AI 输出块 HTML
    // ══════════════════════════════════════════════════════
    function buildAIBlocks(blocks) {
        return blocks.map(function(b) {
            return '<div class="ai-block">'
                + '<div class="ai-block-label"><span class="ai-block-dot" style="background:var(--' + b.color + ')"></span>' + b.label + '</div>'
                + '<div class="ai-text ' + b.color + '">' + b.text + '</div>'
                + '</div>';
        }).join('');
    }
    
    // ══════════════════════════════════════════════════════
    //  解析AI响应
    // ══════════════════════════════════════════════════════
    function parseResponse(text) {
        if (!text) {return [];}
        // 简单解析：按行分割，提取标题和内容
        var lines = text.split('\n').filter(function(l) { return l.trim(); });
        var blocks = [];
        var currentBlock = null;
        
        lines.forEach(function(line) {
            if (line.startsWith('##') || line.startsWith('**')) {
                if (currentBlock) {blocks.push(currentBlock);}
                currentBlock = {
                    label: line.replace(/[#*]/g, '').trim(),
                    text: '',
                    color: 'blue'
                };
            } else if (currentBlock) {
                currentBlock.text += line + '\n';
            }
        });
        
        if (currentBlock) {blocks.push(currentBlock);}
        return blocks;
    }
    
    // ══════════════════════════════════════════════════════
    //  渲染AI响应
    // ══════════════════════════════════════════════════════
    function renderResponse(el, text) {
        var blocks = parseResponse(text);
        el.innerHTML = buildAIBlocks(blocks)
            + '<div class="ai-disclaimer"><span>⚠️</span>以上内容由 AI 辅助生成，仅供参考。</div>';
        el.classList.add('visible');
    }
    
    // ══════════════════════════════════════════════════════
    //  生成双学生对比
    // ══════════════════════════════════════════════════════
    function generateDualRec(stu1, stu2, moduleType) {
        var n1 = stu1 ? (typeof getDisplayName === 'function' ? getDisplayName(stu1) : stu1.name) : '学生A';
        var n2 = stu2 ? (typeof getDisplayName === 'function' ? getDisplayName(stu2) : stu2.name) : '学生B';
        if (typeof toast === 'function') {toast('正在生成 ' + n1 + ' 和 ' + n2 + ' 的对比分析...');}
    }
    
    // ══════════════════════════════════════════════════════
    //  获取 AI Prompt 标识
    // ══════════════════════════════════════════════════════
    function getPromptIdentifier(moduleType) {
        var map = {
            'fitness': '体质健康分析',
            'canteen': '营养餐推荐',
            'activity': '课外活动推荐',
            'reading': '阅读推荐'
        };
        return map[moduleType] || 'AI推荐';
    }
    
    // 公共API
    return {
        generate: generate,
        generateBlocks: _generateBlocks,
        generateDualRec: generateDualRec,
        typewriterEffect: typewriterEffect,
        buildAIBlocks: buildAIBlocks,
        parseResponse: parseResponse,
        renderResponse: renderResponse,
        getPromptIdentifier: getPromptIdentifier
    };
})();

// 兼容全局调用
window.AIToolsModule = AIToolsModule;
window.generateAI = AIToolsModule.generate;
window.generateDynamicAI = AIToolsModule.generate;
window.typewriterEffect = AIToolsModule.typewriterEffect;
window.buildAIBlocks = AIToolsModule.buildAIBlocks;
window.parseAIResponse = AIToolsModule.parseResponse;
window.renderAIResponse = AIToolsModule.renderResponse;
window.generateDualRec = AIToolsModule.generateDualRec;
window.getAIPromptIdentifier = AIToolsModule.getPromptIdentifier;
