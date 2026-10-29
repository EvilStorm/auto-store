// (1) 02 상태 머신 보드의 "등록 후" 체인을 지우고 다시 그린다 (03 스크립트의 잘못된 선 수정).
// (2) Page 3의 모든 섹션에서 직속 자식들을 투명 프레임 "보드" 하나로 감싼다.
//     Figma는 섹션 바로 아래 프레임의 이름을 캔버스에 회색으로 표시하는데, 감싸면 보드당 "보드" 하나만 남는다.
//     여러 번 실행해도 안전하다 (이미 있는 "보드" 프레임을 재사용).
const FAM='Noto Sans KR';
const F=s=>({family:FAM,style:s});
await Promise.all(['Regular','Medium','Bold'].map(s=>figma.loadFontAsync(F(s))));
const page=await figma.getNodeByIdAsync('112:2');
await figma.setCurrentPageAsync(page);
const hex=h=>{const n=parseInt(h.slice(1),16);return{r:((n>>16)&255)/255,g:((n>>8)&255)/255,b:(n&255)/255}};
const solid=h=>({type:'SOLID',color:hex(h)});
function text(str,o={}){const {size=14,style='Regular',color='#1F1F1F',w,align='LEFT',lh}=o;const t=figma.createText();t.fontName=F(style);t.characters=str;t.fontSize=size;t.fills=[solid(color)];if(lh)t.lineHeight={unit:'PIXELS',value:lh};t.textAlignHorizontal=align;if(w){t.resize(w,10);t.textAutoResize='HEIGHT';}return t;}
function label(parent,str,x,y,o={}){const t=text(str,o);t.x=x;t.y=y;parent.appendChild(t);return t;}

// ---------- (1) 02 보드 체인 수정 ----------
const s2=page.children.find(c=>c.type==='SECTION'&&c.name.startsWith('02 '));
let removedChain=0;
if(s2){
  // 이전에 그린 체인 요소: 섹션 직속 또는 "보드" 프레임 안, y >= 720 영역의 pill/선/라벨
  const holder=s2.children.find(c=>c.type==='FRAME'&&c.name==='보드')||s2;
  const names=new Set(['listed','변동 감지','[판매가 수정]','[판매 중지]','[무시]']);
  for(const c of [...holder.children]){
    const isPill=names.has(c.name);
    const isLine=(c.name==='arrow'||c.name==='line')&&c.y>=720;
    const isText=c.type==='TEXT'&&c.y>=720&&(c.characters.startsWith('등록 후')||c.characters.startsWith('suspended 상품은'));
    if(isPill||isLine||isText){c.remove();removedChain++;}
  }
  function pill(x,y,w,t,s,fill,stroke){const f=figma.createFrame();f.name=t;f.resize(w,64);f.x=x;f.y=y;f.fills=[solid(fill)];f.strokes=[solid(stroke)];f.strokeWeight=1;f.cornerRadius=32;f.clipsContent=false;holder.appendChild(f);label(f,t,0,12,{size:14,style:'Bold',w:w,align:'CENTER'});label(f,s,0,36,{size:11,color:'#666666',w:w,align:'CENTER'});return f;}
  function arr(x1,y1,x2,y2,head=true){const pad=8;const minx=Math.min(x1,x2)-pad,miny=Math.min(y1,y2)-pad,w=Math.abs(x2-x1)+pad*2,h=Math.abs(y2-y1)+pad*2;const ax=x1-minx,ay=y1-miny,bx=x2-minx,by=y2-miny;let hd='';if(head){if(x2>x1)hd=`M${bx} ${by} L${bx-8} ${by-4.5} L${bx-8} ${by+4.5} Z`;else if(y2>y1)hd=`M${bx} ${by} L${bx-4.5} ${by-8} L${bx+4.5} ${by-8} Z`;else if(y2<y1)hd=`M${bx} ${by} L${bx-4.5} ${by+8} L${bx+4.5} ${by+8} Z`;else hd=`M${bx} ${by} L${bx+8} ${by-4.5} L${bx+8} ${by+4.5} Z`;}const n=figma.createNodeFromSvg(`<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg"><path d="M${ax} ${ay} L${bx} ${by}" stroke="#8A8A8A" stroke-width="2" fill="none"/>${hd?`<path d="${hd}" fill="#8A8A8A"/>`:''}</svg>`);n.name=head?'arrow':'line';n.x=minx;n.y=miny;holder.appendChild(n);}
  label(holder,'등록 후 (⑩ 감시)',1240,730,{size:13,style:'Bold',color:'#555555'});
  pill(1240,760,180,'listed','관리자 "등록 완료" 표시','#D9F2E3','#2F855A');
  arr(1420,792,1489,792);
  pill(1490,760,200,'변동 감지','가격 · 품절 · 옵션 · MOQ · 삭제','#FFE4C4','#C05621');
  arr(1690,792,1759,792);
  pill(1760,760,180,'[판매가 수정]','→ listed (판매가 갱신)','#FFFFFF','#4A5568');
  pill(1960,760,180,'[판매 중지]','→ suspended','#EDEDED','#9A9A9A');
  pill(2160,760,180,'[무시]','→ listed (확인 처리)','#FFFFFF','#4A5568');
  arr(1590,824,1590,850,false);arr(1590,850,2250,850,false);arr(2050,850,2050,825);arr(2250,850,2250,825);
  label(holder,'suspended 상품은 복구(재판매) 감지 시 다시 알림 → listed',1960,866,{size:11,color:'#666666'});
}

// ---------- (2) 섹션 자식을 "보드" 프레임으로 감싸기 ----------
const wrapped=[];
for(const sec of page.children){
  if(sec.type!=='SECTION')continue;
  let holder=sec.children.find(c=>c.type==='FRAME'&&c.name==='보드');
  if(!holder){holder=figma.createFrame();holder.name='보드';holder.fills=[];holder.strokes=[];holder.clipsContent=false;holder.resize(Math.max(sec.width,1),Math.max(sec.height,1));holder.x=0;holder.y=0;sec.appendChild(holder);}
  else{holder.resize(Math.max(sec.width,1),Math.max(sec.height,1));holder.x=0;holder.y=0;}
  let n=0;
  for(const c of [...sec.children]){
    if(c.id===holder.id)continue;
    const x=c.x,y=c.y;holder.appendChild(c);c.x=x;c.y=y;n++;
  }
  // 감싼 프레임을 맨 뒤(배경)로 두되 섹션 안에 유일한 자식이므로 순서는 그대로
  wrapped.push({section:sec.name,moved:n});
}
return {removedChain,wrapped};
