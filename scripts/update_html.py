"""更新hongkou_v4.html，替换硬编码数据为异步加载"""

with open('g:/EnsureAI/联通/宝山实验/hongkou_v4.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到关键位置
script_data_line = None  # <script src="data.js"></script>
students_start = None    # const STUDENTS = [
students_end = None      # ];
init_start = None        # (async function initStudentService()
init_end = None          # console.log('学生服务层初始化完成');

for i, line in enumerate(lines):
    if '<script src="data.js"></script>' in line:
        script_data_line = i
    if 'const STUDENTS = [' in line and students_start is None:
        students_start = i
    if students_start and i > students_start and line.strip() == '];' and students_end is None:
        students_end = i
    if '(async function initStudentService()' in line and init_start is None:
        init_start = i
    if 'console.log(\'学生服务层初始化完成\');' in line and init_end is None:
        init_end = i

print(f"Found positions:")
print(f"  script data.js: line {script_data_line + 1 if script_data_line else 'NOT FOUND'}")
print(f"  STUDENTS: lines {students_start + 1 if students_start else 'NOT FOUND'} to {students_end + 1 if students_end else 'NOT FOUND'}")
print(f"  initStudentService: lines {init_start + 1 if init_start else 'NOT FOUND'} to {init_end + 1 if init_end else 'NOT FOUND'}")

# 新的数据加载代码
new_data_loading_code = '''<script src="js/api.js"></script>
<script src="https://unpkg.com/dexie@3/dist/dexie.js"></script>
<script src="js/student-service.js"></script>
<script>
// ══════════════════════════════════════════════════════
//  全局数据容器（从 data.json 异步加载）
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
//  异步加载真实数据
// ══════════════════════════════════════════════════════
async function loadRealData() {
    try {
        console.log('正在加载学生数据...');
        const response = await fetch('data.json');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        
        // 加载学生列表
        STUDENTS = data.students || [];
        
        // 加载关联数据
        REAL_DATA = {
            awards_by_student: data.awards_by_student || {},
            clubs_by_student: data.clubs_by_student || {},
            menu_by_week: data.menu_by_week || {},
            fitness_history: data.fitness_history || []
        };
        
        DATA_LOADED = true;
        console.log(`数据加载完成: ${STUDENTS.length}名学生, ${data.total_awards || 0}条获奖, ${data.total_clubs || 0}条社团记录`);
        
        // 初始化学生服务
        await initStudentServiceWithRealData();
        
        // 刷新当前视图
        refreshCurrentView();
        
        return true;
    } catch (error) {
        console.error('加载数据失败:', error);
        toast('数据加载失败，请刷新页面重试');
        return false;
    }
}

// ══════════════════════════════════════════════════════
//  初始化学生服务层（使用真实数据）
// ══════════════════════════════════════════════════════
async function initStudentServiceWithRealData() {
    // 初始化服务
    await StudentService.init();
    
    // 清空现有数据，导入真实数据
    const existingStudents = await StudentService.list();
    if (existingStudents.length > 0) {
        // 清空现有数据
        await StudentService.db.students.clear();
    }
    
    if (STUDENTS.length > 0) {
        console.log('导入真实学生数据到IndexedDB...');
        await StudentService.importFromArray(STUDENTS);
    }
    
    // 同步STUDENTS数组为服务数据（保持兼容性）
    Object.defineProperty(window, 'STUDENTS', {
        get: () => StudentService._memoryCache.filter(s => !s.deleted),
        configurable: true
    });
    
    console.log('学生服务层初始化完成（使用真实数据）');
}

// ══════════════════════════════════════════════════════
//  刷新当前视图
// ══════════════════════════════════════════════════════
function refreshCurrentView() {
    const currentView = document.querySelector('.view.active');
    if (currentView) {
        const viewId = currentView.id;
        if (viewId === 'students') renderStudents();
        else if (viewId === 'dashboard') initDashboard();
        else if (viewId === 'student-detail') {
            const activeStudent = document.querySelector('.student-row.active');
            if (activeStudent) {
                const studentId = activeStudent.dataset.id;
                openStudentById(studentId);
            }
        }
    }
}

// 页面加载时自动加载数据
document.addEventListener('DOMContentLoaded', () => {
    loadRealData();
});

'''

# 构建新的文件内容
new_lines = []

# 添加 script_data_line 之前的内容
if script_data_line:
    new_lines.extend(lines[:script_data_line])

# 添加新的数据加载代码
new_lines.append(new_data_loading_code)

# 跳过旧的代码（script_data_line + 1 到 init_end）
if init_end:
    new_lines.extend(lines[init_end + 1:])
else:
    # 如果没有找到init_end，就从students_end之后开始
    if students_end:
        new_lines.extend(lines[students_end + 1:])

# 写回文件
with open('g:/EnsureAI/联通/宝山实验/hongkou_v4.html', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("文件更新完成！")
print(f"移除了 STUDENTS 硬编码数组和旧的初始化逻辑")
print(f"添加了从 data.json 异步加载真实数据的功能")
