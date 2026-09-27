import * as T from '/vendor/three.module.js';

export class Galaxy {
  constructor(element,onSelect){
    this.el=element;this.onSelect=onSelect;this.data={nodes:[],edges:[]};this.selected=null;
    this.visible=new Set();this.highlight=new Set();this.meshes=new Map();
    this.canvas=element.querySelector('canvas');this.scene=new T.Scene();
    this.renderer=new T.WebGLRenderer({canvas:this.canvas,alpha:true,antialias:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    this.camera=new T.PerspectiveCamera(55,1,1,5000);this.target=new T.Vector3();this.aim=new T.Vector3();
    this.distance=650;this.yaw=0;this.pitch=.2;this.ray=new T.Raycaster();
    this.scene.add(new T.AmbientLight(0xffffff,2));
    this.group=new T.Group();this.scene.add(this.group);
    let down=null;
    this.canvas.addEventListener('pointerdown',e=>{down={x:e.clientX,y:e.clientY,moved:false};this.canvas.setPointerCapture(e.pointerId)});
    this.canvas.addEventListener('pointermove',e=>{if(!down)return;const dx=e.clientX-down.x,dy=e.clientY-down.y;
      if(Math.abs(dx)+Math.abs(dy)>2)down.moved=true;this.yaw-=dx*.006;this.pitch=Math.max(-1.3,Math.min(1.3,this.pitch+dy*.006));down.x=e.clientX;down.y=e.clientY});
    this.canvas.addEventListener('pointerup',e=>{if(down&&!down.moved){const r=this.canvas.getBoundingClientRect();
      this.ray.setFromCamera(new T.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),this.camera);
      const hits=this.ray.intersectObjects([...this.meshes.values()].filter(m=>m.visible));
      if(hits[0])this.select(hits[0].object.userData.id)}down=null});
    this.canvas.addEventListener('wheel',e=>{e.preventDefault();this.distance=Math.max(90,Math.min(1800,this.distance+e.deltaY*.5))},{passive:false});
    this.canvas.tabIndex=0;this.canvas.setAttribute('aria-label','3D knowledge graph. Arrow keys rotate; plus and minus zoom. Use node list to select.');
    this.canvas.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')this.yaw-=.12;else if(e.key==='ArrowRight')this.yaw+=.12;
      else if(e.key==='ArrowUp')this.pitch=Math.min(1.3,this.pitch+.12);else if(e.key==='ArrowDown')this.pitch=Math.max(-1.3,this.pitch-.12);
      else if(e.key==='+'||e.key==='=')this.distance=Math.max(90,this.distance-40);else if(e.key==='-')this.distance=Math.min(1800,this.distance+40);else return;e.preventDefault()});
    element.querySelector('[data-act=expand]').onclick=()=>this.expand();
    element.querySelector('[data-act=collapse]').onclick=()=>{if(this.selected){this.visible=new Set([this.selected]);this.renderVisibility()}};
    element.querySelector('[data-act=all]').onclick=()=>{this.visible=new Set(this.data.nodes.map(n=>n.id));this.target.set(0,0,0);this.distance=650;this.renderVisibility()};
    this.animate();
  }
  setData(data){
    this.data=data;this.meshes.clear();
    for(const child of [...this.group.children]){child.geometry?.dispose();child.material?.map?.dispose();child.material?.dispose();this.group.remove(child)}
    data.nodes.forEach((n,i)=>{const phi=Math.acos(1-2*(i+.5)/Math.max(1,data.nodes.length)),theta=i*2.39996;
      const radius=n.kind==='DOCUMENT'?220:300;const mesh=new T.Mesh(new T.SphereGeometry(n.kind==='DOCUMENT'?10:6,16,12),new T.MeshBasicMaterial({color:n.kind==='DOCUMENT'?0x7bffd5:0x7aa7e8}));
      mesh.position.set(Math.sin(phi)*Math.cos(theta)*radius,Math.cos(phi)*radius,Math.sin(phi)*Math.sin(theta)*radius);
      mesh.userData.id=n.id;this.meshes.set(n.id,mesh);this.group.add(mesh);
      const canvas=document.createElement('canvas');canvas.width=512;canvas.height=64;const c=canvas.getContext('2d');c.font='22px sans-serif';c.fillStyle='#d8f9ef';c.textAlign='center';c.fillText(n.label.slice(0,36),256,38);
      const sprite=new T.Sprite(new T.SpriteMaterial({map:new T.CanvasTexture(canvas),transparent:true}));sprite.position.copy(mesh.position).add(new T.Vector3(0,18,0));sprite.scale.set(130,16,1);sprite.userData.node=n.id;this.group.add(sprite);
    });
    this.edges=[];
    data.edges.forEach(e=>{const a=this.meshes.get(e.subject),b=this.meshes.get(e.object);if(!a||!b)return;
      const line=new T.Line(new T.BufferGeometry().setFromPoints([a.position,b.position]),new T.LineBasicMaterial({color:0x579b8b,transparent:true,opacity:.15+.55*e.confidence}));
      line.userData.edge=e;this.edges.push(line);this.group.add(line)});
    this.visible=new Set(data.nodes.map(n=>n.id));this.renderVisibility();
  }
  renderVisibility(){
    this.group.children.forEach(o=>{o.visible=o.userData.edge ? this.visible.has(o.userData.edge.subject)&&this.visible.has(o.userData.edge.object):this.visible.has(o.userData.id||o.userData.node)});
    for(const [id,m] of this.meshes){m.material.color.setHex(this.highlight.has(id)||id===this.selected?0xffcf7d:this.data.nodes.find(n=>n.id===id)?.kind==='DOCUMENT'?0x7bffd5:0x7aa7e8);m.scale.setScalar(this.highlight.has(id)?1.6:1)}
    const list=this.el.querySelector('#galaxy-list');list.replaceChildren();
    for(const n of this.data.nodes.filter(n=>this.visible.has(n.id))){const b=document.createElement('button');b.textContent=n.label;b.onclick=()=>this.select(n.id);list.append(b)}
    this.el.querySelector('#galaxy-caption').textContent=`${this.visible.size} nodes · ${this.edges.filter(e=>e.visible).length} supported links\nDrag to orbit · scroll to zoom · gold = retrieved source · brighter edge = stronger evidence`;
  }
  select(id){
    const node=this.data.nodes.find(n=>n.id===id);if(!node)return;
    this.selected=id;this.target.copy(this.meshes.get(id).position);this.distance=340;this.renderVisibility();
    const pane=this.el.querySelector('#galaxy-inspect');pane.replaceChildren();
    const title=document.createElement('b');title.textContent=node.label+' · '+node.kind;pane.append(title);
    if(node.kind==='DOCUMENT'){const b=document.createElement('button');b.textContent='Open source';b.onclick=()=>this.onSelect(id,true);pane.append(document.createElement('br'),b);this.onSelect(id,false)}
    for(const e of this.data.edges.filter(e=>e.subject===id||e.object===id)){
      const b=document.createElement('button');b.textContent=`${e.predicate} · evidence: ${e.evidence}`;
      b.onclick=()=>this.onSelect(e.subject,true);pane.append(document.createElement('br'),b)}
  }
  expand(){if(!this.selected)return;for(const e of this.data.edges)if(e.subject===this.selected||e.object===this.selected){this.visible.add(e.subject);this.visible.add(e.object)}this.renderVisibility()}
  focus(ids){this.highlight=new Set(ids);for(const id of ids)this.visible.add(id);const m=ids.map(id=>this.meshes.get(id)).filter(Boolean);if(m.length){this.target.set(0,0,0);for(const p of m)this.target.add(p.position);this.target.divideScalar(m.length);this.distance=480}this.renderVisibility()}
  animate(){requestAnimationFrame(()=>this.animate());if(this.el.hidden)return;
    const w=this.el.clientWidth,h=this.el.clientHeight;if(!w||!h)return;
    this.renderer.setSize(w,h,false);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();this.aim.lerp(this.target,.06);
    this.camera.position.set(this.aim.x+Math.sin(this.yaw)*Math.cos(this.pitch)*this.distance,this.aim.y+Math.sin(this.pitch)*this.distance,this.aim.z+Math.cos(this.yaw)*Math.cos(this.pitch)*this.distance);this.camera.lookAt(this.aim);this.renderer.render(this.scene,this.camera)}
}
