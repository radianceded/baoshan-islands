/**
 * Toast Component - 独立消息提示组件
 * 完全自包含，不依赖任何外部状态
 */
const Toast = (function() {
    'use strict';
    
    let timer = null;
    let el = null;
    let initialized = false;
    
    /**
     * 初始化 DOM 元素
     */
    function init() {
        if (initialized) {return;}
        
        el = document.createElement('div');
        el.id = 'toast-component';
        
        // 内联样式，完全独立
        const style = document.createElement('style');
        style.textContent = `
            #toast-component {
                position: fixed;
                bottom: 28px;
                left: 50%;
                transform: translateX(-50%);
                background: #111827;
                color: white;
                padding: 11px 20px;
                border-radius: 8px;
                font-size: 13px;
                font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
                box-shadow: 0 8px 32px rgba(0,0,0,0.25);
                z-index: 99999;
                display: none;
                opacity: 0;
                transition: opacity 0.25s ease;
                white-space: nowrap;
                pointer-events: none;
                max-width: 80vw;
            }
            #toast-component.visible {
                display: block;
                opacity: 1;
            }
        `;
        
        document.head.appendChild(style);
        document.body.appendChild(el);
        initialized = true;
        
        console.log('[Toast] 组件初始化完成');
    }
    
    /**
     * 显示消息
     * @param {string} msg - 消息内容
     * @param {number} duration - 显示时长（毫秒），默认 1000ms
     */
    function show(msg, duration) {
        // 延迟初始化，确保 DOM 已就绪
        if (!initialized) {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => show(msg, duration));
                return;
            }
            init();
        }
        
        // 清除之前的定时器
        if (timer) {
            clearTimeout(timer);
            timer = null;
        }
        
        // 设置内容并显示
        el.textContent = msg;
        el.style.display = 'block';
        
        // 强制重排确保过渡动画生效
        void el.offsetHeight;
        
        el.style.opacity = '1';
        
        // 自动隐藏
        const hideDelay = duration || 1000;
        timer = setTimeout(() => {
            el.style.opacity = '0';
            
            // 等待过渡完成后隐藏元素
            setTimeout(() => {
                if (el) {el.style.display = 'none';}
            }, 250);
        }, hideDelay);
        
        console.log(`[Toast] 显示: "${msg}" (${hideDelay}ms)`);
    }
    
    /**
     * 立即隐藏
     */
    function hide() {
        if (timer) {
            clearTimeout(timer);
            timer = null;
        }
        if (el) {
            el.style.opacity = '0';
            setTimeout(() => {
                if (el) {el.style.display = 'none';}
            }, 250);
        }
    }
    
    // 公共 API
    return {
        init,
        show,
        hide
    };
})();

// 全局暴露（兼容旧代码）
window.Toast = Toast;
window.toast = Toast.show;

console.log('[Toast] 模块加载完成');
