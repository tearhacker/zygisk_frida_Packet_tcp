/*
 * ksu.js —— KernelSU WebUI 注入对象的薄封装。
 *
 * 为什么自己写而不用官方 npm 包 `kernelsu`：
 *   1. 官方包是 ESM，而页面若以 file:// 加载，origin 为 null，
 *      <script type="module"> 会被 CORS 拦截导致整页失效。
 *   2. 官方包本体不到 3KB，且只是 ksu.exec / ksu.spawn 的转发，无额外收益。
 *   3. 本工程不希望为一个面板引入 node 构建链。
 *   详见 ../../docs/10-施工指导/ZygiskAIRuntime_模块WebUI设计_v1.0.md §3
 *
 * 本文件用 classic script 暴露全局 window.KSU，不使用任何模块语法。
 */
(function (global) {
  'use strict';

  var counter = 0;

  function callbackName(prefix) {
    counter += 1;
    return prefix + '_cb_' + Date.now().toString(36) + '_' + counter;
  }

  function drop(name) {
    try {
      delete global[name];
    } catch (e) {
      global[name] = undefined;
    }
  }

  /** ksu 桥接是否可用（普通浏览器 / Magisk 环境下为 false）。 */
  function isAvailable() {
    return typeof global.ksu !== 'undefined' && typeof global.ksu.exec === 'function';
  }

  /**
   * 执行 shell 命令。
   * @returns {Promise<{errno:number, stdout:string, stderr:string}>}
   */
  function exec(command, options, timeoutMs) {
    if (!isAvailable()) {
      return Promise.reject(new Error('KSU_BRIDGE_UNAVAILABLE'));
    }
    var opts = options || {};
    var timeout = timeoutMs || 15000;

    return new Promise(function (resolve, reject) {
      var name = callbackName('exec');
      var settled = false;
      var timer = null;

      function finish(fn, value) {
        if (settled) return;
        settled = true;
        if (timer !== null) clearTimeout(timer);
        drop(name);
        fn(value);
      }

      global[name] = function (errno, stdout, stderr) {
        finish(resolve, {
          errno: typeof errno === 'number' ? errno : -1,
          stdout: typeof stdout === 'string' ? stdout : '',
          stderr: typeof stderr === 'string' ? stderr : ''
        });
      };

      timer = setTimeout(function () {
        finish(reject, new Error('EXEC_TIMEOUT'));
      }, timeout);

      try {
        global.ksu.exec(command, JSON.stringify(opts), name);
      } catch (e) {
        finish(reject, e);
      }
    });
  }

  /** 原生返回的多半是 JSON 字符串，这里统一容错成 JS 值。 */
  function parseMaybe(raw) {
    if (raw === null || raw === undefined) return null;
    if (typeof raw !== 'string') return raw;
    try {
      return JSON.parse(raw);
    } catch (e) {
      return raw;
    }
  }

  function callRaw(fnName, args) {
    if (!isAvailable() || typeof global.ksu[fnName] !== 'function') return null;
    try {
      return global.ksu[fnName].apply(global.ksu, args || []);
    } catch (e) {
      return null;
    }
  }

  /** 已安装包名列表；取不到返回空数组（不伪造）。 */
  function listPackages(type) {
    var raw = callRaw('listPackages', type === undefined ? [] : [type]);
    if (raw === null) {
      raw = callRaw('listPackages', []);
    }
    var parsed = parseMaybe(raw);
    return Object.prototype.toString.call(parsed) === '[object Array]' ? parsed : [];
  }

  /** 包名 -> 应用信息；取不到返回空数组。 */
  function getPackagesInfo(packages) {
    var raw = callRaw('getPackagesInfo', [JSON.stringify(packages || [])]);
    var parsed = parseMaybe(raw);
    return Object.prototype.toString.call(parsed) === '[object Array]' ? parsed : [];
  }

  function moduleInfo() {
    return parseMaybe(callRaw('moduleInfo', []));
  }

  function toast(message) {
    callRaw('toast', [message]);
  }

  global.KSU = {
    isAvailable: isAvailable,
    exec: exec,
    listPackages: listPackages,
    getPackagesInfo: getPackagesInfo,
    moduleInfo: moduleInfo,
    toast: toast
  };
})(window);
