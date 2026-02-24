(function () {
  const state = {
    data: null,
    step: 0,
    timer: null,
    fps: 8,
    flowId: null,
    metric: "stress",
    leftKey: null,
    rightKey: null,
  };

  const ui = {
    status: document.getElementById("statusText"),
    loadBtn: document.getElementById("loadDefaultBtn"),
    fileInput: document.getElementById("fileInput"),
    playBtn: document.getElementById("playBtn"),
    pauseBtn: document.getElementById("pauseBtn"),
    speedInput: document.getElementById("speedInput"),
    speedText: document.getElementById("speedText"),
    stepInput: document.getElementById("stepInput"),
    stepText: document.getElementById("stepText"),
    flowSelect: document.getElementById("flowSelect"),
    metricSelect: document.getElementById("metricSelect"),
    titleLeft: document.getElementById("titleLeft"),
    titleRight: document.getElementById("titleRight"),
    metricsLeft: document.getElementById("metricsLeft"),
    metricsRight: document.getElementById("metricsRight"),
    svgLeft: document.getElementById("svgLeft"),
    svgRight: document.getElementById("svgRight"),
  };

  const ns = "http://www.w3.org/2000/svg";
  const pad = 70;
  const size = 760;

  function edgeKey(a, b) {
    return a < b ? `${a}-${b}` : `${b}-${a}`;
  }

  function lerpColor(a, b, t) {
    const aa = parseInt(a.slice(1), 16);
    const bb = parseInt(b.slice(1), 16);
    const ar = (aa >> 16) & 255;
    const ag = (aa >> 8) & 255;
    const ab = aa & 255;
    const br = (bb >> 16) & 255;
    const bg = (bb >> 8) & 255;
    const bbv = bb & 255;
    const rr = Math.round(ar + (br - ar) * t);
    const rg = Math.round(ag + (bg - ag) * t);
    const rb = Math.round(ab + (bbv - ab) * t);
    return `rgb(${rr}, ${rg}, ${rb})`;
  }

  function colorForValue(v, vmax) {
    const t = Math.max(0, Math.min(1, vmax <= 0 ? 0 : v / vmax));
    return lerpColor("#c9e7ea", "#cc4c2b", Math.pow(t, 0.7));
  }

  function scenarioKeys() {
    return Object.keys(state.data.scenarios);
  }

  function snapshotFor(key, step) {
    return state.data.scenarios[key].snapshots[step];
  }

  function maxStep() {
    const key = scenarioKeys()[0];
    return state.data.scenarios[key].snapshots.length - 1;
  }

  function metricVmax(metricName) {
    let vmax = 0.0001;
    for (const key of scenarioKeys()) {
      for (const snap of state.data.scenarios[key].snapshots) {
        for (const v of snap[metricName]) {
          if (v > vmax) vmax = v;
        }
      }
    }
    return vmax;
  }

  function clearSvg(svg) {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
  }

  function createSvgGroup(svg, tag) {
    const g = document.createElementNS(ns, "g");
    g.setAttribute("data-group", tag);
    svg.appendChild(g);
    return g;
  }

  function genericLayout(topology) {
    const span = size - 2 * pad;
    const xs = topology.nodes.map((n) => Number(n.x));
    const ys = topology.nodes.map((n) => Number(n.y));
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const dx = Math.max(maxX - minX, 1e-9);
    const dy = Math.max(maxY - minY, 1e-9);
    return topology.nodes.reduce((acc, n) => {
      const x = pad + ((Number(n.x) - minX) / dx) * span;
      const y = pad + ((Number(n.y) - minY) / dy) * span;
      acc[n.id] = { x, y };
      return acc;
    }, {});
  }

  function buildScene(svg, titleEl, scenarioKey) {
    clearSvg(svg);
    titleEl.textContent = scenarioKey;
    const topology = state.data.topology;
    const pos = genericLayout(topology);

    const gEdges = createSvgGroup(svg, "edges");
    const gPath = createSvgGroup(svg, "path");
    const gNodes = createSvgGroup(svg, "nodes");

    const edgeMap = new Map();
    for (const [u, v] of topology.edges) {
      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", String(pos[u].x));
      line.setAttribute("y1", String(pos[u].y));
      line.setAttribute("x2", String(pos[v].x));
      line.setAttribute("y2", String(pos[v].y));
      line.setAttribute("stroke", "#9eb5bb");
      line.setAttribute("stroke-width", "1.4");
      line.setAttribute("opacity", "0.72");
      gEdges.appendChild(line);
      edgeMap.set(edgeKey(u, v), line);
    }

    const nodeMap = new Map();
    for (const node of topology.nodes) {
      const c = document.createElementNS(ns, "circle");
      c.setAttribute("cx", String(pos[node.id].x));
      c.setAttribute("cy", String(pos[node.id].y));
      c.setAttribute("r", "7");
      c.setAttribute("fill", "#c3dde1");
      c.setAttribute("stroke", "#2b4b52");
      c.setAttribute("stroke-width", "1");
      gNodes.appendChild(c);
      nodeMap.set(node.id, c);
    }

    const pathPoly = document.createElementNS(ns, "polyline");
    pathPoly.setAttribute("fill", "none");
    pathPoly.setAttribute("stroke", "#d8871a");
    pathPoly.setAttribute("stroke-width", "6");
    pathPoly.setAttribute("stroke-linecap", "round");
    pathPoly.setAttribute("stroke-linejoin", "round");
    pathPoly.setAttribute("opacity", "0.92");
    gPath.appendChild(pathPoly);

    const pathUnder = document.createElementNS(ns, "polyline");
    pathUnder.setAttribute("fill", "none");
    pathUnder.setAttribute("stroke", "#1e3036");
    pathUnder.setAttribute("stroke-width", "9");
    pathUnder.setAttribute("stroke-linecap", "round");
    pathUnder.setAttribute("stroke-linejoin", "round");
    pathUnder.setAttribute("opacity", "0.28");
    gPath.insertBefore(pathUnder, pathPoly);

    const legend = document.createElementNS(ns, "text");
    legend.setAttribute("x", "20");
    legend.setAttribute("y", "32");
    legend.setAttribute("class", "legend");
    legend.textContent = "Path:";
    svg.appendChild(legend);

    return { pos, edgeMap, nodeMap, pathPoly, pathUnder, legend, scenarioKey };
  }

  let leftScene = null;
  let rightScene = null;

  function updateMetrics(container, snap) {
    const chips = [
      `V(S): ${snap.v_s.toFixed(4)}`,
      `Loss: ${snap.loss}`,
      `PDR: ${(snap.pdr * 100).toFixed(1)}%`,
      `Delay: ${snap.avg_delay.toFixed(2)}`,
      `AvgHop: ${snap.avg_hop.toFixed(2)}`,
      `Reroute: ${snap.route_changes}`,
      `TableUpd: ${snap.table_updates}`,
      `Broadcast: ${snap.broadcasts || 0}`,
    ];
    container.innerHTML = chips.map((t) => `<div class="metric-chip">${t}</div>`).join("");
  }

  function applyFailureStyle(scene, step) {
    for (const line of scene.edgeMap.values()) {
      line.setAttribute("stroke", "#9eb5bb");
      line.setAttribute("stroke-dasharray", "");
      line.setAttribute("opacity", "0.72");
    }
    const failures = state.data.scenarios[scene.scenarioKey].failure_events || [];
    for (const evt of failures) {
      if (step >= evt.step) {
        const k = edgeKey(evt.edge[0], evt.edge[1]);
        const line = scene.edgeMap.get(k);
        if (line) {
          line.setAttribute("stroke", "#bf3f32");
          line.setAttribute("stroke-dasharray", "6 5");
          line.setAttribute("opacity", "0.95");
        }
      }
    }
  }

  function pathToPoints(path, pos) {
    return path.map((id) => `${pos[id].x},${pos[id].y}`).join(" ");
  }

  function renderScene(scene, snap, metricName) {
    const vmax = metricVmax(metricName);
    const values = snap[metricName];
    let localMax = 0;
    for (const v of values) if (v > localMax) localMax = v;

    for (const [id, c] of scene.nodeMap.entries()) {
      c.setAttribute("fill", colorForValue(values[id], vmax));
    }

    applyFailureStyle(scene, snap.step);

    const route = snap.flow_paths[state.flowId];
    if (route && route.path.length > 1) {
      const points = pathToPoints(route.path, scene.pos);
      scene.pathPoly.setAttribute("points", points);
      scene.pathUnder.setAttribute("points", points);
      scene.pathPoly.setAttribute("stroke", route.ok ? "#d8871a" : "#bf3f32");
      scene.legend.textContent = `Path ${state.flowId} | hops=${route.path.length - 1} | ${
        route.ok ? "reachable" : "loop/broken"
      } | max(${metricName})=${localMax.toFixed(3)}`;
    } else {
      scene.pathPoly.setAttribute("points", "");
      scene.pathUnder.setAttribute("points", "");
      scene.legend.textContent = `Path ${state.flowId} | no route`;
    }
  }

  function render() {
    if (!state.data) return;
    const leftSnap = snapshotFor(state.leftKey, state.step);
    const rightSnap = snapshotFor(state.rightKey, state.step);
    renderScene(leftScene, leftSnap, state.metric);
    renderScene(rightScene, rightSnap, state.metric);
    updateMetrics(ui.metricsLeft, leftSnap);
    updateMetrics(ui.metricsRight, rightSnap);
    ui.stepText.textContent = `${state.step} / ${maxStep()}`;
    ui.stepInput.value = String(state.step);
    const deltaPdr = (rightSnap.pdr - leftSnap.pdr) * 100;
    const deltaLoss = rightSnap.loss - leftSnap.loss;
    const topo = state.data.meta && state.data.meta.topology_kind ? state.data.meta.topology_kind : "unknown";
    ui.status.textContent =
      `topology=${topo} | step=${state.step} | flow=${state.flowId} | metric=${state.metric} | ` +
      `ΔPDR(SNN-baseline)=${deltaPdr.toFixed(2)}% | ΔLoss=${deltaLoss}`;
  }

  function stopPlay() {
    if (state.timer) clearInterval(state.timer);
    state.timer = null;
  }

  function play() {
    stopPlay();
    state.timer = setInterval(() => {
      state.step = (state.step + 1) % (maxStep() + 1);
      render();
    }, Math.max(20, Math.floor(1000 / state.fps)));
  }

  function setupControls() {
    ui.stepInput.max = String(maxStep());
    ui.stepInput.value = "0";
    ui.stepText.textContent = `0 / ${maxStep()}`;

    const flows = state.data.scenarios[state.leftKey].probe_flows || [];
    ui.flowSelect.innerHTML = "";
    for (const f of flows) {
      const opt = document.createElement("option");
      opt.value = f.id;
      opt.textContent = `${f.id}`;
      ui.flowSelect.appendChild(opt);
    }
    state.flowId = flows.length > 0 ? flows[0].id : null;
  }

  function initScenes() {
    const keys = scenarioKeys();
    state.leftKey = keys[0];
    state.rightKey = keys.length > 1 ? keys[1] : keys[0];
    leftScene = buildScene(ui.svgLeft, ui.titleLeft, state.leftKey);
    rightScene = buildScene(ui.svgRight, ui.titleRight, state.rightKey);
  }

  async function loadDefault() {
    try {
      const res = await fetch("../run_dir/snn_route_viz.json");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      mountData(data);
    } catch (err) {
      ui.status.textContent =
        "默认数据加载失败。请在仓库根目录启动 `python3 -m http.server` 后打开页面，或手动选择 JSON 文件。";
    }
  }

  function mountData(data) {
    state.data = data;
    state.step = 0;
    initScenes();
    setupControls();
    render();
  }

  ui.loadBtn.addEventListener("click", loadDefault);
  ui.fileInput.addEventListener("change", async (evt) => {
    const file = evt.target.files && evt.target.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      mountData(JSON.parse(text));
    } catch (_e) {
      ui.status.textContent = "文件解析失败，请确认是有效的 snn_route_viz.json。";
    }
  });
  ui.playBtn.addEventListener("click", play);
  ui.pauseBtn.addEventListener("click", stopPlay);
  ui.stepInput.addEventListener("input", (evt) => {
    state.step = Number(evt.target.value);
    render();
  });
  ui.speedInput.addEventListener("input", (evt) => {
    state.fps = Number(evt.target.value);
    ui.speedText.textContent = `${state.fps} FPS`;
    if (state.timer) play();
  });
  ui.flowSelect.addEventListener("change", (evt) => {
    state.flowId = evt.target.value;
    render();
  });
  ui.metricSelect.addEventListener("change", (evt) => {
    state.metric = evt.target.value;
    render();
  });

  loadDefault();
})();
