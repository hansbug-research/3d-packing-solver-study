# Three.js 数据层 smoke test

该 fixture 复现报告中 Node 24 + Three.js r185 的非渲染测试：创建 10,000 个 `InstancedMesh` 实例，计算 bounds，执行 instance picking，并设置 clipping plane。它不创建 WebGL renderer，因此输出不能解释为 FPS、显存或桌面 WebView 性能。

```bash
npm ci
npm run smoke
```

实验输出和 `/usr/bin/time -v` 资源记录归档在 `raw/experiments/frontend-three-smoke/`。升级 Node 或 Three.js 后应重新生成并记录 lockfile 与结果。
