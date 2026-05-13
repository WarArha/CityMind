"""
CityMind GUI — Elite Responsive Operations Dashboard
===========================================
Frontend-only aesthetic + layout upgrade. Backend challenge modules are untouched.

Key UI fixes:
  • Responsive topbar/sidebar/log sizing from the live window dimensions.
  • Scrollable clipped sidebar so controls never run off-screen.
  • Clipped map canvas so panned/zoomed grid elements never draw outside panel.
  • Premium dark dashboard palette with cards, rounded corners, shadows,
    hover feedback, and compact status chips.
"""

import pygame, sys, os, io, threading, time
from contextlib import redirect_stdout
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from challenge1 import CityGraph, CityLayoutManager, ConstraintChecker, LOCATION_TYPES, LABELS
from challenge2 import RoadNetworkBuilder
from challenge4 import EmergencyMission, run_challenge4

# ── Premium Design Tokens ─────────────────────────────────────────────────────
C = {
    "bg": (7, 10, 22),
    "bg2": (10, 16, 34),
    "panel": (18, 25, 48),
    "panel2": (24, 34, 64),
    "sidebar": (11, 17, 36),
    "grid_bg": (13, 19, 39),
    "grid_line": (46, 59, 95),
    "text": (234, 240, 255),
    "text_dim": (142, 154, 190),
    "muted": (87, 99, 136),
    "accent": (92, 140, 255),
    "accent2": (49, 211, 142),
    "accent3": (180, 110, 255),
    "warn": (255, 189, 74),
    "danger": (245, 91, 104),
    "success": (61, 220, 151),
    "Residential": (48, 120, 202),
    "Hospital": (238, 85, 103),
    "School": (244, 190, 70),
    "Industrial": (191, 120, 68),
    "PowerPlant": (172, 93, 232),
    "AmbulanceDepot": (57, 211, 142),
    None: (34, 45, 76),
    "road_mst": (79, 184, 255),
    "road_backup": (255, 162, 76),
    "road_other": (60, 76, 118),
    "road_blocked": (245, 79, 94),
    "btn": (30, 42, 76),
    "btn_hover": (44, 61, 105),
    "btn_active": (78, 125, 255),
    "btn_fix": (40, 148, 104),
    "btn_danger": (155, 55, 70),
    "btn_text": (238, 243, 255),
    "shadow": (0, 0, 0),
}
SHORT={"Residential":"RES","Hospital":"HSP","School":"SCH",
       "Industrial":"IND","PowerPlant":"PWR","AmbulanceDepot":"AMB",None:""}

# ── Responsive Layout Tokens ──────────────────────────────────────────────────
SIDEBAR_MIN  = 230
SIDEBAR_MAX  = 310
TOPBAR_MIN   = 58
TOPBAR_MAX   = 74
LOG_MIN      = 150
LOG_MAX      = 230
RIGHT_PANEL_MIN = 260
RIGHT_PANEL_MAX = 340
CELL_MARGIN  = 14
CELL_SZ_MIN  = 42
CELL_SZ_MAX  = 118


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def draw_shadow_rect(surf, rect, radius=14, alpha=70, offset=(0, 6)):
    """Soft pseudo-shadow built with a translucent rounded rectangle."""
    shadow = pygame.Surface((rect.w + 18, rect.h + 18), pygame.SRCALPHA)
    pygame.draw.rect(shadow, (*C["shadow"], alpha),
                     pygame.Rect(9 + offset[0], 9 + offset[1], rect.w, rect.h),
                     border_radius=radius)
    surf.blit(shadow, (rect.x - 9, rect.y - 9))


def draw_card(surf, rect, fill=None, border=None, radius=16, shadow=True):
    if shadow:
        draw_shadow_rect(surf, rect, radius=radius, alpha=45, offset=(0, 5))
    pygame.draw.rect(surf, fill or C["panel"], rect, border_radius=radius)
    pygame.draw.rect(surf, border or C["grid_line"], rect, 1, border_radius=radius)


def get_right_panel_width(screen):
    """Right inspector panel is shown only when there is enough width."""
    W, H = screen.get_size()
    if W < 1120:
        return 0
    return clamp(int(W * 0.22), RIGHT_PANEL_MIN, min(RIGHT_PANEL_MAX, max(250, W // 3)))


def get_dims(screen):
    """Return responsive layout metrics from live screen size.

    Layout is a presentation dashboard:
      left command rail + center map/log + optional right intelligence panel.
    The center canvas never draws under the side panels, which fixes overflow.
    """
    W, H = screen.get_size()
    sw = clamp(int(W * 0.19), SIDEBAR_MIN, min(SIDEBAR_MAX, max(190, W // 3)))
    rw = get_right_panel_width(screen)
    th = clamp(int(H * 0.078), TOPBAR_MIN, TOPBAR_MAX)
    lh = clamp(int(H * 0.235), LOG_MIN, min(LOG_MAX, max(120, H // 3)))
    if H < 640:
        lh = clamp(int(H * 0.20), 110, 150)
        th = clamp(int(H * 0.075), 48, 58)
    gx, gy = sw, th
    gw = max(260, W - sw - rw)
    gh = max(180, H - th - lh)
    return W, H, sw, th, lh, gx, gy, gw, gh

def lerp_color(c1, c2, t):
    """Linearly interpolate between two RGB colors (t in 0..1)."""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def draw_glow_line(surf, p1, p2, color, width, glow_alpha=55):
    """Draw a road segment with a soft neon glow halo."""
    glow = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    pygame.draw.line(glow, (*color, glow_alpha), p1, p2, width + 8)
    surf.blit(glow, (0, 0))
    pygame.draw.line(surf, color, p1, p2, width)
    # bright inner line
    bright = tuple(min(255, v + 80) for v in color)
    pygame.draw.line(surf, bright, p1, p2, max(1, width - 2))


def draw_node_3d(surf, rect, base_color, border_radius=8):
    """Pseudo-3D node: dark side offset + main face + top-left shimmer."""
    # Shadow
    shadow_surf = pygame.Surface((rect.w + 6, rect.h + 6), pygame.SRCALPHA)
    pygame.draw.rect(shadow_surf, (0, 0, 0, 70),
                     pygame.Rect(4, 5, rect.w, rect.h), border_radius=border_radius)
    surf.blit(shadow_surf, (rect.x - 2, rect.y - 2))
    # Dark side face (depth illusion)
    side = pygame.Rect(rect.x + 3, rect.y + 3, rect.w, rect.h)
    dark = tuple(max(0, c - 55) for c in base_color)
    pygame.draw.rect(surf, dark, side, border_radius=border_radius)
    # Main face
    pygame.draw.rect(surf, base_color, rect, border_radius=border_radius)
    # Top-left shimmer
    shimmer = pygame.Surface((rect.w, rect.h // 3 + 2), pygame.SRCALPHA)
    pygame.draw.rect(shimmer, (255, 255, 255, 28),
                     pygame.Rect(0, 0, rect.w, rect.h // 3 + 2), border_radius=border_radius)
    surf.blit(shimmer, rect.topleft)


_font_cache = {}
def make_fonts(H):
    """Scaled font set with sensible laptop/projector bounds."""
    key = H // 16
    if key not in _font_cache:
        base  = clamp(H // 48, 14, 19)
        small = clamp(H // 58, 11, 16)
        big   = clamp(H // 32, 20, 30)
        tiny  = clamp(H // 68, 9, 13)
        _font_cache[key] = (
            pygame.font.SysFont("Segoe UI", base),
            pygame.font.SysFont("Segoe UI", small),
            pygame.font.SysFont("Segoe UI Semibold", big, bold=True),
            pygame.font.SysFont("Segoe UI", tiny),
        )
    return _font_cache[key]

# ── Button ────────────────────────────────────────────────────────────────────
class Button:
    def __init__(self, rect, label, color=None, hcolor=None, tcolor=None, acolor=None):
        self.rect  = pygame.Rect(rect)
        self.label = label
        self.col   = color  or C["btn"]
        self.hcol  = hcolor or C["btn_hover"]
        self.tcol  = tcolor or C["btn_text"]
        self.acol  = acolor or C["btn_active"]
        self.hover = False; self.active = False; self.on = True

    def draw(self, surf, font):
        rect = self.rect
        c = self.acol if self.active else self.hcol if self.hover else self.col
        if not self.on:
            c = tuple(max(0, v - 42) for v in self.col)
        if rect.w <= 0 or rect.h <= 0:
            return
        if self.hover or self.active:
            draw_shadow_rect(surf, rect, radius=10, alpha=55, offset=(0, 4))
        pygame.draw.rect(surf, c, rect, border_radius=10)
        border = C["accent"] if self.active else (65, 82, 126)
        pygame.draw.rect(surf, border, rect, 1, border_radius=10)
        if self.active:
            pygame.draw.rect(surf, C["accent2"],
                             pygame.Rect(rect.x + 7, rect.y + 7, 4, rect.h - 14),
                             border_radius=4)
        label = self.label
        while font.size(label)[0] > rect.w - 22 and len(label) > 4:
            label = label[:-2] + "…"
        t = font.render(label, True, C["text_dim"] if not self.on else self.tcol)
        surf.blit(t, t.get_rect(center=rect.center))

    def update(self, pos): self.hover = self.rect.collidepoint(pos) and self.on
    def hit(self, pos, ev):
        return self.on and ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1 and self.rect.collidepoint(pos)

# ── InputBox ──────────────────────────────────────────────────────────────────
class InputBox:
    def __init__(self, rect, label, default="0", maxc=5):
        self.rect=pygame.Rect(rect); self.label=label
        self.text=str(default); self.maxc=maxc; self.focus=False
    def handle(self, ev):
        if ev.type==pygame.MOUSEBUTTONDOWN: self.focus=self.rect.collidepoint(ev.pos)
        if ev.type==pygame.KEYDOWN and self.focus:
            if ev.key==pygame.K_BACKSPACE: self.text=self.text[:-1]
            elif ev.unicode.isdigit() and len(self.text)<self.maxc: self.text+=ev.unicode
    def val(self):
        try: return int(self.text)
        except: return 0
    def draw(self, surf, font, sf):
        surf.blit(sf.render(self.label,True,C["text_dim"]),(self.rect.x,self.rect.y-18))
        bc=C["accent"] if self.focus else (66, 80, 122)
        draw_shadow_rect(surf,self.rect,radius=9,alpha=25,offset=(0,3))
        pygame.draw.rect(surf,C["panel2"],self.rect,border_radius=9)
        pygame.draw.rect(surf,bc,self.rect,1,border_radius=9)
        t=font.render(self.text or "0",True,C["text"])
        surf.blit(t,(self.rect.x+9,self.rect.centery-t.get_height()//2))


# ── Setup Screen ──────────────────────────────────────────────────────────────
class SetupScreen:
    def __init__(self, screen):
        self.screen=screen; self.done=False; self.result=None; self.err=""
        self._rebuild()

    def _rebuild(self):
        W,H=self.screen.get_size()
        self.font,self.sf,self.bf,_=make_fonts(H)
        cx=W//2; L=cx-290; R=cx+30; y0=int(H*0.16)
        self.r  =InputBox((L,     y0,90, 32),"Grid Rows","5")
        self.c  =InputBox((L+110, y0,90, 32),"Grid Cols","5")
        self.bt =InputBox((R,     y0,110,32),"Max Backtrack","500",6)
        self.mc =InputBox((R+130, y0,110,32),"Max MinConflict","1000",6)
        defs={"Residential":"6","Hospital":"2","School":"2",
              "Industrial":"2","PowerPlant":"2","AmbulanceDepot":"1"}
        self.ti={}
        for i,t in enumerate(LOCATION_TYPES):
            col=L if i%2==0 else R
            row=y0+68+(i//2)*64
            self.ti[t]=InputBox((col,row,200,32),t,defs.get(t,"0"))
        by=y0+68+(len(LOCATION_TYPES)//2)*64+28
        self.go=Button((cx-110,by,220,44),"LAUNCH CITYMIND",
                       color=(48,196,130),hcolor=(60,215,148),
                       acolor=(48,196,130),tcolor=(10,20,14))

    def handle(self, ev):
        W,H=self.screen.get_size()
        if ev.type==pygame.VIDEORESIZE: self._rebuild(); return
        for b in [self.r,self.c,self.bt,self.mc]: b.handle(ev)
        for b in self.ti.values(): b.handle(ev)
        pos=pygame.mouse.get_pos(); self.go.update(pos)
        if self.go.hit(pos,ev): self._launch()

    def _launch(self):
        rows=self.r.val(); cols=self.c.val()
        bt=self.bt.val(); mc=self.mc.val()
        tc={t:b.val() for t,b in self.ti.items() if b.val()>0}
        if rows<2 or cols<2: self.err="Grid must be at least 2x2"; return
        if not tc: self.err="Enter at least one node count"; return
        if bt<1 or mc<1: self.err="Budgets must be >= 1"; return
        self.result=(rows,cols,sum(tc.values()),tc,bt,mc); self.done=True

    def draw(self):
        W,H=self.screen.get_size()
        self.screen.fill(C["bg"])
        t=self.bf.render("CityMind  --  Setup",True,C["accent"])
        self.screen.blit(t,t.get_rect(centerx=W//2,y=int(H*0.05)))
        s=self.sf.render("Configure your city, then click LAUNCH",True,C["text_dim"])
        self.screen.blit(s,s.get_rect(centerx=W//2,y=int(H*0.10)))
        pygame.draw.line(self.screen,C["grid_line"],(W//2-320,int(H*0.13)),(W//2+320,int(H*0.13)),1)
        for b in [self.r,self.c,self.bt,self.mc]: b.draw(self.screen,self.font,self.sf)
        self.screen.blit(self.sf.render("Location type counts:",True,C["text"]),(W//2-290,int(H*0.245)))
        for tn,box in self.ti.items():
            pygame.draw.rect(self.screen,C.get(tn,C["text_dim"]),(box.rect.x-12,box.rect.y+10,8,8))
            box.draw(self.screen,self.font,self.sf)
        self.go.draw(self.screen,self.font)
        if self.err:
            e=self.font.render(self.err,True,C["danger"])
            self.screen.blit(e,e.get_rect(centerx=W//2,y=self.go.rect.bottom+10))


# ── Loading Screen ─────────────────────────────────────────────────────────────
class LoadingScreen:
    def __init__(self, screen, rows, cols, num_nodes, tc, bt, mc):
        self.screen=screen; self.manager=None; self.csp_log=""
        self.done=False; self.tick=0; self.log_lines=[]
        def _run():
            mgr=CityLayoutManager(); buf=io.StringIO()
            mgr._interactive_resolve=lambda v: None
            with redirect_stdout(buf): mgr.initialize(rows,cols,num_nodes,tc,bt,mc)
            self.csp_log=buf.getvalue(); self.manager=mgr; self.done=True
        threading.Thread(target=_run,daemon=True).start()

    def update(self):
        self.tick+=1
        if self.csp_log:
            lines=[l.strip() for l in self.csp_log.splitlines() if l.strip()]
            self.log_lines=lines[-6:]

    def draw(self):
        W,H=self.screen.get_size(); cx,cy=W//2,H//2
        _,sf,bf,_=make_fonts(H)
        self.screen.fill(C["bg"])
        angle=(self.tick*5)%360
        for i in range(12):
            a=angle+i*30; v=pygame.math.Vector2(1,0).rotate(a)
            ax=cx+int(40*v.x); ay=cy-100+int(40*v.y)
            col=tuple(int(ch*(i/12)) for ch in C["accent"])
            pygame.draw.circle(self.screen,col,(ax,ay),6)
        dots="."*((self.tick//15)%4)
        t=bf.render(f"Building your city{dots}",True,C["accent"])
        self.screen.blit(t,t.get_rect(centerx=cx,y=cy-35))
        for i,line in enumerate(self.log_lines):
            safe=line.encode("ascii","replace").decode("ascii")
            col=C["text"] if i==len(self.log_lines)-1 else C["text_dim"]
            s=sf.render(safe[:110],True,col)
            self.screen.blit(s,s.get_rect(centerx=cx,y=cy+20+i*22))
        h=sf.render("CSP solver running in background...",True,C["text_dim"])
        self.screen.blit(h,h.get_rect(centerx=cx,y=cy+160))


# ── Violation Panel (scrollable) ───────────────────────────────────────────────
class ViolationPanel:
    """
    Scrollable overlay panel showing all violations + clickable fix buttons.
    Mouse wheel scrolls content. Nothing is clipped.
    """
    def __init__(self, screen, manager, violations):
        self.screen=screen; self.manager=manager
        self.violations=violations; self.done=False; self.result_log=[]
        self.scroll=0   # pixels scrolled down

        self.rule_hits={"Rule1":0,"Rule2":0,"Rule3":0}
        for v in violations:
            for k in self.rule_hits:
                if k in v: self.rule_hits[k]+=1

        self._build()

    def _panel_rect(self):
        W,H=self.screen.get_size()
        pw=min(820,W-80); ph=min(680,H-60)
        return W//2-pw//2, H//2-ph//2, pw, ph

    def _build(self):
        self.fixes=[]
        rd={"Rule1":"Industrial adjacent to School/Hospital",
            "Rule2":"Residential too far from Hospital (>3 hops)",
            "Rule3":"PowerPlant too far from Industrial (>2 hops)"}
        if self.rule_hits["Rule1"]>0:
            self.fixes.append(("Expand grid by 2 cols (more room for Industrial separation)",
                               lambda:self._fix(lambda:self.manager.city.expand_grid(2))))
            self.fixes.append(("Reduce Industrial count by 1",
                               lambda:self._fix(lambda:self._reduce("Industrial",1))))
        if self.rule_hits["Rule2"]>0:
            self.fixes.append(("Add 1 Hospital (improves Residential coverage)",
                               lambda:self._fix(lambda:self._add_type("Hospital",1))))
            self.fixes.append(("Reduce Residential count by 2",
                               lambda:self._fix(lambda:self._reduce("Residential",2))))
        if self.rule_hits["Rule3"]>0:
            self.fixes.append(("Add 1 Industrial (anchors nearby PowerPlants)",
                               lambda:self._fix(lambda:self._add_type("Industrial",1))))
            self.fixes.append(("Reduce PowerPlant count by 1",
                               lambda:self._fix(lambda:self._reduce("PowerPlant",1))))
        self.fixes.append(("Keep min-conflict layout as-is and continue",None))

    def _reduce(self,loc_type,n):
        removed=0
        for nid in list(reversed(self.manager.city.active_nodes)):
            if removed>=n: break
            if self.manager.city.assignment.get(nid)==loc_type:
                self.manager.city.active_nodes.remove(nid)
                self.manager.city.assignment[nid]=None; removed+=1
        self.manager.type_counts[loc_type]=max(0,self.manager.type_counts.get(loc_type,0)-removed)

    def _add_type(self,loc_type,n):
        for _ in range(n):
            empty=self.manager.city.get_empty_cells()
            if not empty:
                self.manager.city.expand_grid(max(1,self.manager.city.cols//2))
                empty=self.manager.city.get_empty_cells()
            best=min(empty,key=lambda cell:sum(
                abs(self.manager.city.coords(cell)[0]-self.manager.city.coords(nd)[0])+
                abs(self.manager.city.coords(cell)[1]-self.manager.city.coords(nd)[1])
                for nd in self.manager.city.active_nodes) if self.manager.city.active_nodes else 0)
            self.manager.city.active_nodes.append(best)
        self.manager.type_counts[loc_type]=self.manager.type_counts.get(loc_type,0)+n

    def _fix(self,action):
        action()
        from challenge1 import CSPSolver
        for nid in self.manager.city.active_nodes:
            self.manager.city.assignment[nid]=None
        solver=CSPSolver(self.manager.city,self.manager.checker,
                         self.manager.type_counts,self.manager.max_bt,self.manager.max_mc)
        ok=solver.solve()
        if ok: self.result_log.append("Fix applied: CSP solved — no violations remain.")
        else:
            _,viols=solver.find_minimum_conflict_solution()
            self.result_log.append(f"Fix applied: {len(viols)} violation(s) remain.")
        self.manager.city.build_road_network(); self.done=True

    def handle(self,ev):
        W,H=self.screen.get_size()
        px,py,pw,ph=self._panel_rect()
        _,sf,_,_=make_fonts(H)

        # Scroll with mouse wheel inside panel
        if ev.type==pygame.MOUSEWHEEL:
            if pygame.Rect(px,py,pw,ph).collidepoint(pygame.mouse.get_pos()):
                self.scroll=max(0,self.scroll-ev.y*22)
                # clamp immediately
                bh=36; gap=8
                total_h=(self._content_header_height(sf)
                         +len(self.fixes)*(bh+gap)+20)
                self.scroll=min(self.scroll,max(0,total_h-ph+50))

        if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
            panel_rect=pygame.Rect(px,py,pw,ph)

            # Click outside = dismiss safely (no crash)
            if not panel_rect.collidepoint(ev.pos):
                self.result_log.append("Kept min-conflict layout.")
                self.done=True
                return

            # Hit-test fix buttons (accounting for scroll offset)
            header_h=self._content_header_height(sf)
            btn_start_y=py+header_h+4-self.scroll
            bw=pw-48; bh=36; gap=8
            for i,(lbl,cb) in enumerate(self.fixes):
                br=pygame.Rect(px+24, btn_start_y+i*(bh+gap), bw, bh)
                if br.collidepoint(ev.pos):
                    if cb is None:
                        self.result_log.append("Kept min-conflict layout.")
                        self.done=True
                    else:
                        cb()
                    return

    def _content_header_height(self,sf):
        """
        Height from cy=py+46 to where fix buttons start.
        Must match draw() exactly so handle() hit-tests the right positions.
        """
        rule_lines=sum(1 for cnt in self.rule_hits.values() if cnt>0)
        viol_lines=len(self.violations)
        # rule lines: 22px each
        # gap: 6
        # "All N violations:" label: 20
        # violation lines: 18px each
        # gap: 12
        # "Choose a fix" label: 26
        return rule_lines*22 + 6 + 20 + viol_lines*18 + 12 + 26

    def draw(self):
        W,H=self.screen.get_size()
        px,py,pw,ph=self._panel_rect()
        font,sf,bf,_=make_fonts(H)

        # Dim background overlay
        ov=pygame.Surface((W,H),pygame.SRCALPHA)
        ov.fill((0,0,0,170))
        self.screen.blit(ov,(0,0))

        # Panel background + border
        pygame.draw.rect(self.screen,C["panel"],(px,py,pw,ph),border_radius=10)
        pygame.draw.rect(self.screen,C["danger"],(px,py,pw,ph),2,border_radius=10)

        # Fixed title bar (not scrolled)
        t=bf.render("Constraint Violations Detected",True,C["danger"])
        self.screen.blit(t,(px+20,py+12))
        pygame.draw.line(self.screen,C["grid_line"],(px+10,py+44),(px+pw-10,py+44),1)

        # Set clip to panel body (below title line)
        clip=pygame.Rect(px+2,py+46,pw-4,ph-48)
        self.screen.set_clip(clip)

        rd={"Rule1":"Industrial adjacent to School / Hospital",
            "Rule2":"Residential too far from Hospital (> 3 hops)",
            "Rule3":"PowerPlant too far from Industrial (> 2 hops)"}

        # All content starts at py+46, then scrolled up by self.scroll
        cy=py+46-self.scroll

        # Rule summary lines
        for rule,cnt in self.rule_hits.items():
            if cnt>0:
                msg=f"  {rule}: {rd[rule]}  ({cnt} violation(s))"
                self.screen.blit(sf.render(msg,True,C["warn"]),(px+20,cy))
                cy+=22

        cy+=6
        self.screen.blit(sf.render(f"All {len(self.violations)} violation(s):",
                         True,C["text_dim"]),(px+20,cy))
        cy+=20

        for v in self.violations:
            safe=v.encode("ascii","replace").decode("ascii")
            self.screen.blit(sf.render("  "+safe[:105],True,C["text_dim"]),(px+20,cy))
            cy+=18

        cy+=12
        self.screen.blit(font.render("Choose a fix to apply:",True,C["text"]),(px+20,cy))
        cy+=26

        # Fix buttons — cy here is the exact same start point handle() uses
        bw=pw-48; bh=36; gap=8
        pos=pygame.mouse.get_pos()
        for i,(lbl,cb) in enumerate(self.fixes):
            br=pygame.Rect(px+24, cy+i*(bh+gap), bw, bh)
            col=C["btn_fix"] if cb else C["btn"]
            hovered=br.collidepoint(pos)
            draw_col=tuple(min(255,v+30) for v in col) if hovered else col
            pygame.draw.rect(self.screen,draw_col,br,border_radius=6)
            lt=sf.render(lbl,True,(255,255,255))
            self.screen.blit(lt,lt.get_rect(center=br.center))

        self.screen.set_clip(None)

        # Scrollbar
        total_h=(cy-py-46+self.scroll)+len(self.fixes)*(bh+gap)+20
        if total_h>ph-46:
            visible_h=ph-46
            sb_h=max(28,int(visible_h*visible_h/total_h))
            max_scroll=max(0,total_h-visible_h)
            self.scroll=min(self.scroll,max_scroll)
            frac=self.scroll/max(1,max_scroll)
            sb_y=py+46+int((visible_h-sb_h)*frac)
            pygame.draw.rect(self.screen,C["grid_line"],(px+pw-9,py+46,6,visible_h),border_radius=3)
            pygame.draw.rect(self.screen,C["accent"],(px+pw-9,sb_y,6,sb_h),border_radius=3)


# ── Hospital Picker ────────────────────────────────────────────────────────────
class HospitalPicker:
    def __init__(self, screen, city):
        self.screen=screen; self.city=city
        self.chosen=None; self.done=False

    def handle(self, ev, geom_fn):
        W,H=self.screen.get_size(); _,_,sw,th,_,_,_,_,_=get_dims(self.screen)
        _,sf,_,_=make_fonts(H)
        font,_,_,_=make_fonts(H)
        pos=pygame.mouse.get_pos()
        # Cancel button
        cbr=pygame.Rect(W-130,H-60,110,36)
        if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
            if cbr.collidepoint(pos): self.done=True; return
            ox,oy,sz=geom_fn()
            c=(pos[0]-ox)//sz; r=(pos[1]-oy)//sz
            if 0<=r<self.city.rows and 0<=c<self.city.cols:
                nid=self.city.node_id(r,c)
                if self.city.assignment.get(nid)=="Hospital":
                    self.chosen=nid; self.done=True

    def draw(self):
        W,H=self.screen.get_size()
        _,_,sw,th,_,_,_,_,_=get_dims(self.screen)
        font,sf,bf,_=make_fonts(H)
        # Banner across grid area
        bh=56
        pygame.draw.rect(self.screen,(20,15,8,230),(sw,th,W-sw,bh))
        pygame.draw.rect(self.screen,C["warn"],(sw,th,W-sw,bh),2)
        msg=bf.render("Click a HOSPITAL (red) cell to set it as Primary Hospital",True,C["warn"])
        self.screen.blit(msg,msg.get_rect(centerx=(sw+(W-sw)//2),y=th+14))
        # Cancel button
        cbr=pygame.Rect(W-130,H-60,110,36)
        pygame.draw.rect(self.screen,C["btn_danger"],cbr,border_radius=6)
        ct=font.render("Cancel",True,(255,255,255))
        self.screen.blit(ct,ct.get_rect(center=cbr.center))


# ── Civilian Picker (Ch4) ─────────────────────────────────────────────────────
class CivilianPicker:
    """
    Modal overlay for selecting civilian waypoints (Challenge 4).
    Click any active node to add it as a civilian; click again to remove.
    Up to MAX_CIVILIANS allowed.  'Start Mission' confirms selection.
    """
    MAX_CIVILIANS = 5

    def __init__(self, screen, city, start_node):
        self.screen    = screen
        self.city      = city
        self.start     = start_node
        self.civilians = []   # list of selected node IDs in click order
        self.done      = False
        self.cancelled = False

    def handle(self, ev, geom_fn):
        if ev.type != pygame.MOUSEBUTTONDOWN or ev.button != 1:
            return
        pos = pygame.mouse.get_pos()
        W, H = self.screen.get_size()

        cancel_r = pygame.Rect(W - 120, H - 58, 104, 34)
        clear_r  = pygame.Rect(W - 236, H - 58, 104, 34)
        start_r  = pygame.Rect(W - 380, H - 58, 132, 34)

        if cancel_r.collidepoint(pos):
            self.cancelled = True; self.done = True; return
        if clear_r.collidepoint(pos):
            self.civilians = []; return
        if start_r.collidepoint(pos):
            if self.civilians:
                self.done = True
            return

        ox, oy, sz = geom_fn()
        if sz <= 0: return
        c = (pos[0] - ox) // sz
        r = (pos[1] - oy) // sz
        if 0 <= r < self.city.rows and 0 <= c < self.city.cols:
            nid = self.city.node_id(r, c)
            if nid == self.start:
                return                               # start node cannot be a civilian
            if self.city.assignment.get(nid) is None:
                return                               # empty cell
            if nid in self.civilians:
                self.civilians.remove(nid)           # deselect
            elif len(self.civilians) < self.MAX_CIVILIANS:
                self.civilians.append(nid)           # select

    def draw(self):
        W, H = self.screen.get_size()
        _, _, sw, th, _, _, _, _, _ = get_dims(self.screen)
        font, sf, bf, _ = make_fonts(H)

        # Banner
        bh = 58
        pygame.draw.rect(self.screen, (8, 12, 6, 230), (sw, th, W - sw, bh))
        pygame.draw.rect(self.screen, C["danger"],      (sw, th, W - sw, bh), 2)
        n   = len(self.civilians)
        msg = bf.render(
            f"Click nodes to mark trapped civilians  ({n}/{self.MAX_CIVILIANS})  "
            f"— click again to deselect",
            True, C["danger"])
        self.screen.blit(msg, msg.get_rect(centerx=(sw + (W - sw) // 2), y=th + 16))

        # Buttons at bottom-right
        cancel_r = pygame.Rect(W - 120, H - 58, 104, 34)
        clear_r  = pygame.Rect(W - 236, H - 58, 104, 34)
        start_r  = pygame.Rect(W - 380, H - 58, 132, 34)

        pygame.draw.rect(self.screen, C["btn_danger"], cancel_r, border_radius=6)
        self.screen.blit(font.render("Cancel", True, (255, 255, 255)),
                         font.render("Cancel", True, (255,255,255)).get_rect(center=cancel_r.center))

        pygame.draw.rect(self.screen, C["btn"], clear_r, border_radius=6)
        self.screen.blit(font.render("Clear All", True, (255, 255, 255)),
                         font.render("Clear All", True,(255,255,255)).get_rect(center=clear_r.center))

        ok_col = C["accent2"] if self.civilians else C["btn"]
        pygame.draw.rect(self.screen, ok_col, start_r, border_radius=6)
        self.screen.blit(font.render(f"Start Mission ({n})", True, (255, 255, 255)),
                         font.render(f"Start Mission ({n})", True,(255,255,255)).get_rect(center=start_r.center))


# ── Main GUI ──────────────────────────────────────────────────────────────────
class CityMindGUI:
    VIEWS=["City Layout","Road Network","Ambulance","Emergency","Crime Risk"]

    def __init__(self, screen, manager, bt, mc, csp_log=""):
        self.screen=screen; self.manager=manager; self.city=manager.city
        self.bt=bt; self.mc=mc
        self.view="City Layout"; self.selected=None
        self.popup=None; self.log=[]; self.road_builder=None
        self.primary_hospital_id=None  # node ID of user-selected primary hospital; tracked through GA swaps
        self.violation_panel=None; self.hospital_picker=None
        # Ch3/4/5 hooks
        self.ambulance_nodes=[]; self.emergency_route=[]; self.crime_risk={}
        # Ch4 emergency mission state
        self._em_mission  = None   # EmergencyMission instance
        self._em_picker   = None   # CivilianPicker instance
        self._em_start    = None   # start node for current mission
        self._em_btn      = None   # reference to the Emergency action button
        self._ch5_pipeline=None; self._ch5_deployment={}
        self._ch5_predictions={}; self._ch5_importances={}
        self._amb_coverage={}; self._ga_worst=None; self._ga_gens=None
        # Scrollable log/sidebar state
        self.log_scroll=0   # 0=bottom (newest), positive=scrolled up
        self.sidebar_scroll=0
        self._sidebar_content_bottom=0
        # Pan/zoom for map
        self.pan_x=0; self.pan_y=0; self.zoom=1.0
        self._panning=False; self._pan_start=None; self._pan_origin=None
        self._pending_view=None  # set from background threads; applied on next draw
        self._picker_blocked_edges=None  # blocked_edges held for a forced HospitalPicker re-prompt
        self._sim_running=False          # true while one simulation step is executing
        self._sim_auto_running=False     # true during 5-7 sec slow auto mode
        self._sim_controller=None        # CityMindIntegrationSimulation stepper instance
        self._sim_state=None             # current/final SimulationState from integration_simulation.py

        for line in csp_log.splitlines():
            cl=line.strip()
            if cl and any(k in cl for k in ["Solved","conflict","Rule","Grid","CSP","Active"]):
                self.log.append(cl.encode("ascii","replace").decode("ascii"))
        if not self.log: self.log.append("City layout loaded successfully.")

        ok,viols=manager.checker.full_check(manager.city.assignment,manager.city.active_nodes)
        if not ok:
            self.violation_panel=ViolationPanel(screen,manager,viols)
            self.log.append(f"WARNING: {len(viols)} constraint violation(s) — see panel.")

        self._build_ui()

    def _build_ui(self):
        W,H=self.screen.get_size()
        _,_,sw,th,lh,_,_,_,_=get_dims(self.screen)
        font,sf,bf,_=make_fonts(H)
        pad = 14
        body_top = th + 18 - int(getattr(self, "sidebar_scroll", 0))
        btn_w = max(80, sw - pad*2)
        view_h = 40
        action_h = 34 if H >= 720 else 31
        gap = 9 if H >= 720 else 7

        self.vbtns=[]
        y = body_top + 28
        for i,v in enumerate(self.VIEWS):
            btn=Button((pad,y,btn_w,view_h),v)
            btn.active=(v==self.view); self.vbtns.append((v,btn))
            y += view_h + gap

        action_list=[
            ("Add Node",        self._act_add),
            ("Replace Node",    self._act_replace),
            ("Build Roads",     self._act_build_roads),
            ("Block Road",      self._act_block_road),
            ("Validate",        self._act_validate),
            ("Place Ambulances",self._act_ambulances),
            ("Emergency Setup", self._act_emergency),
            ("Run Crime Risk",  self._act_crime_risk),
            ("Start Step Sim",  self._act_integration_sim),
            ("Next Sim Step",   self._act_next_sim_step),
            ("Auto Slow Sim",   self._act_auto_slow_sim),
        ]
        y += 30
        self.abtns=[]
        for i,(lbl,cb) in enumerate(action_list):
            if i == 8:          # gap before SIMULATION section header
                y += 22
            col = C["panel2"]
            if "Sim" in lbl: col = (35, 55, 106)
            btn=Button((pad,y,btn_w,action_h),lbl,color=col)
            self.abtns.append((btn,cb))
            if cb is self._act_emergency:
                self._em_btn=btn
            y += action_h + gap
        # If right inspector is visible, keep the sidebar lean; otherwise keep
        # stats/legend inside the scrollable command rail for smaller screens.
        self._sidebar_content_bottom = y + (72 if get_right_panel_width(self.screen) else 370)
        visible_h = max(1, H - th - 10)
        max_scroll = max(0, self._sidebar_content_bottom - (th + visible_h))
        self.sidebar_scroll = clamp(getattr(self, "sidebar_scroll", 0), 0, max_scroll)

    def _geom(self):
        W,H=self.screen.get_size()
        _,_,sw,th,lh,gx,gy,gw,gh=get_dims(self.screen)
        city=self.city; pad=48
        base_sz=max(CELL_SZ_MIN,min(CELL_SZ_MAX,
                    min((gw-pad*2)//max(city.cols,1),
                        (gh-pad*2)//max(city.rows,1))))
        sz=int(base_sz*self.zoom)
        sz=max(20,min(400,sz))
        # Centre of grid in grid canvas, then apply pan
        cx=gx+gw//2; cy=gy+gh//2
        ox=cx-(sz*city.cols)//2+self.pan_x
        oy=cy-(sz*city.rows)//2+self.pan_y
        return ox,oy,sz

    # ── Events ───────────────────────────────────────────────────────
    def handle(self, ev):
        W,H=self.screen.get_size()
        _,_,sw,th,lh,gx,gy,gw,gh=get_dims(self.screen)

        if ev.type==pygame.VIDEORESIZE:
            self._build_ui(); return

        if self.violation_panel and not self.violation_panel.done:
            self.violation_panel.handle(ev)
            if self.violation_panel.done:
                for msg in self.violation_panel.result_log: self._log(msg)
                self.violation_panel=None
            return

        if self.hospital_picker and not self.hospital_picker.done:
            self.hospital_picker.handle(ev,self._geom)
            if self.hospital_picker.done:
                chosen=self.hospital_picker.chosen
                self.hospital_picker=None
                forced_blocked=self._picker_blocked_edges
                self._picker_blocked_edges=None
                if forced_blocked is not None:
                    # Picker was opened by auto-rebuild (primary lost); route through that path
                    if chosen is not None:
                        self._do_auto_rebuild_with_hospital(chosen,forced_blocked)
                    else:
                        # User cancelled forced re-prompt — fall back to first available hospital
                        fallback=next((n for n in self.city.active_nodes
                                       if self.city.assignment.get(n)=="Hospital"),None)
                        if fallback:
                            self._log(f"▶▶ Re-selection cancelled — falling back to "
                                      f"{self.city.coords(fallback)} as Primary Hospital.")
                            self._do_auto_rebuild_with_hospital(fallback,forced_blocked)
                        else:
                            self._log("Re-selection cancelled and no hospital found. Roads not rebuilt.")
                else:
                    # Normal user-initiated road build
                    if chosen is not None: self._do_build_roads(chosen)
                    else: self._log("Road build cancelled.")
            return

        if self._em_picker and not self._em_picker.done:
            self._em_picker.handle(ev,self._geom)
            if self._em_picker.done:
                p=self._em_picker; self._em_picker=None
                if not p.cancelled and p.civilians:
                    self._start_em_mission(p.start,p.civilians)
                else:
                    self._log("Emergency setup cancelled.")
            return

        if self.popup: self._popup_ev(ev,pygame.mouse.get_pos()); return

        pos=pygame.mouse.get_pos()
        in_grid=(pos[0]>gx and pos[0]<gx+gw and pos[1]>th and pos[1]<H-lh)
        log_y=H-lh

        # ── Mouse wheel: scroll sidebar/log OR zoom grid ───────────────
        if ev.type==pygame.MOUSEWHEEL:
            if pos[0] < sw:
                visible_h = max(1, H - th - 10)
                max_scroll = max(0, getattr(self, "_sidebar_content_bottom", H) - (th + visible_h))
                self.sidebar_scroll = clamp(getattr(self, "sidebar_scroll", 0) - ev.y*36, 0, max_scroll)
                self._build_ui()
            elif pos[1]>log_y:
                self.log_scroll=max(0,self.log_scroll+ev.y)
                self.log_scroll=min(self.log_scroll,max(0,len(self.log)-1))
            elif in_grid:
                factor=1.1 if ev.y>0 else 0.9
                self.zoom=max(0.3,min(5.0,self.zoom*factor))
            return

        # ── Middle-mouse / right-mouse drag = pan ─────────────────────
        if ev.type==pygame.MOUSEBUTTONDOWN and ev.button in (2,3) and in_grid:
            self._panning=True; self._pan_start=pos
            self._pan_origin=(self.pan_x,self.pan_y); return
        if ev.type==pygame.MOUSEBUTTONUP and ev.button in (2,3):
            self._panning=False; return
        if ev.type==pygame.MOUSEMOTION and self._panning:
            if self._pan_start:
                dx=pos[0]-self._pan_start[0]; dy=pos[1]-self._pan_start[1]
                self.pan_x=self._pan_origin[0]+dx
                self.pan_y=self._pan_origin[1]+dy
            return

        # Reset zoom/pan on double-click in grid
        if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1 and in_grid:
            mods=pygame.key.get_mods()
            if mods & pygame.KMOD_CTRL:
                self.zoom=1.0; self.pan_x=0; self.pan_y=0
                self._log("Map reset to default zoom/pan  (Ctrl+click)")
                return

        for view,btn in self.vbtns:
            btn.update(pos)
            if btn.hit(pos,ev): self._set_view(view)

        for btn,cb in self.abtns:
            btn.update(pos)
            if btn.hit(pos,ev): cb()

        if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
            ox,oy,sz=self._geom()
            if sz>0:
                c=(pos[0]-ox)//sz; r=(pos[1]-oy)//sz
                if 0<=r<self.city.rows and 0<=c<self.city.cols:
                    self.selected=(r,c)
                    nid=self.city.node_id(r,c)
                    loc=self.city.assignment.get(nid) or "empty"
                    self._log(f"Selected ({r},{c}): {loc}")

    # ── Challenge 3 ─────────────────────────────────────────────────
    def _act_ambulances(self):
        """Run GA ambulance placement (Challenge 3) in a background thread."""
        if not self.city.active_nodes:
            self._log("ERROR: No city loaded."); return

        # Count AmbulanceDepot nodes on the grid
        depot_count = sum(1 for n in self.city.active_nodes
                          if self.city.assignment.get(n) == "AmbulanceDepot")

        # Must have exactly 3 AmbulanceDepot nodes (spec: 3 ambulances)
        if depot_count < 3:
            self._log(f"ERROR: Only {depot_count} Ambulance Depot node(s) on grid.")
            self._log(f"  -> You need exactly 3 AmbulanceDepot nodes.")
            self._log(f"  -> Currently have: {depot_count} — need {3-depot_count} more.")
            self._log(f"  -> Use Add Node -> AmbulanceDepot to add more.")
            return

        if depot_count > 3:
            self._log(f"ERROR: Too many Ambulance Depot nodes ({depot_count} on grid).")
            self._log(f"  -> Exactly 3 are required — you have {depot_count-3} extra.")
            self._log(f"  -> Use Replace Node to change the extra depot(s) to another type.")
            return

        self._log("Ch3: Building distance matrix (fast, done once)...")
        self._set_view("Ambulance")
        import threading
        threading.Thread(target=self._run_ch3, daemon=True).start()

    def _run_ch3(self):
        """
        Background thread:
        - Precomputes distance matrix (slow step, done once)
        - Runs GA entirely
        - Sets ambulance_nodes ONLY after ALL generations complete
          so the GUI never shows intermediate/partial placements
        - Updates node counts in sidebar
        """
        try:
            from challenge3 import run_challenge3
            matrix_built = [False]

            def progress(gen, worst):
                if gen == 0 and not matrix_built[0]:
                    self._log("  Distance matrix ready. GA evolving...")
                    matrix_built[0] = True
                elif gen > 0 and gen % 25 == 0:
                    self._log(f"  GA gen {gen}: worst-case dist = {worst:.2f}")

            ga = run_challenge3(self.city, callback=progress)

            # Build coverage map (instant — uses precomputed matrix)
            coverage = {}
            for nid, amb, dist in ga.coverage_report():
                coverage[nid] = dist

            # ── Swap existing AmbulanceDepot nodes to GA best positions ──
            #
            # Logic:
            #   old_depots  = current positions of the 3 AmbulanceDepot nodes
            #   best_spots  = 3 node IDs GA found as optimal positions
            #
            # For each best_spot that is NOT already a depot:
            #   - The node currently at best_spot gets the type of one old depot
            #     (its type is displaced to the old depot position)
            #   - The old depot position receives the displaced type
            #   - best_spot becomes AmbulanceDepot
            #
            # Net result: grid still has the same set of location types,
            # the 3 AmbulanceDepot nodes have simply moved to better positions.

            old_depots = [n for n in self.city.active_nodes
                          if self.city.assignment.get(n) == "AmbulanceDepot"]
            best_spots = ga.best_placement[:]

            # Depots that are already at an optimal spot stay put
            already_optimal = [n for n in old_depots if n in best_spots]
            depots_to_move  = [n for n in old_depots if n not in best_spots]
            spots_to_fill   = [n for n in best_spots if n not in old_depots]

            # Pair each depot-to-move with a spot-to-fill and swap types.
            # Also track if the primary hospital is displaced so roads can follow it.
            new_ph_id = self.primary_hospital_id  # will be updated if hospital moves

            for depot_nid, target_nid in zip(depots_to_move, spots_to_fill):
                displaced_type = self.city.assignment.get(target_nid)
                depot_coords   = self.city.coords(depot_nid)
                target_coords  = self.city.coords(target_nid)

                # Move depot to target; old depot position receives displaced type
                self.city.assignment[target_nid] = "AmbulanceDepot"
                self.city.assignment[depot_nid]  = displaced_type

                self._log(f"  Depot {depot_coords} -> {target_coords} "
                          f"(swapped with {displaced_type})")

                # If the primary hospital was at target_nid it has now moved to depot_nid
                if target_nid == new_ph_id:
                    new_ph_id = depot_nid
                    self._log(f"  Primary Hospital followed: {target_coords} -> {depot_coords}")

            # type_counts stay the same — same number of each type, just rearranged
            # (no increment/decrement needed because it's a pure swap)

            # Persist updated primary hospital reference before rebuilding roads
            self.primary_hospital_id = new_ph_id

            # Atomic GUI update — shown only now, after all swaps are done
            self._amb_coverage   = coverage
            self._ga_worst       = ga.best_worst_case
            self._ga_gens        = ga.generations_run
            self.ambulance_nodes = ga.best_placement[:]  # triggers Ambulance view

            self._log(f"Ch3 complete: {ga.generations_run} gens, "
                      f"worst-case dist = {ga.best_worst_case:.2f}")
            coords = [self.city.coords(n) for n in ga.best_placement]
            self._log(f"Final ambulance positions: {coords}")

            # Auto-rebuild roads using updated primary hospital (Ch2 integration)
            # Done inline — no pygame calls here (background thread)
            blocked = self._save_blocked_edges()
            b = self.road_builder
            if b is not None:
                ph_id = new_ph_id
                if ph_id is None or self.city.assignment.get(ph_id) != "Hospital":
                    ph_id = next((n for n in self.city.active_nodes
                                  if self.city.assignment.get(n) == "Hospital"), None)
                    if ph_id is not None:
                        self.primary_hospital_id = ph_id
                ad = next((n for n in self.city.active_nodes
                           if self.city.assignment.get(n) == "AmbulanceDepot"), None)
                if ph_id is not None and ad is not None:
                    b.primary_hospital = ph_id; b.ambulance_depot = ad
                    buf2 = io.StringIO()
                    with redirect_stdout(buf2):
                        all_edges = b._get_candidate_edges()
                        b._run_kruskals(all_edges)
                        b._second_path_augmentation()
                        b._write_to_city_graph(blocked_edges=blocked)
                    self._log(f"Roads auto-rebuilt after ambulance placement.")
                    self._log(f"  Primary Hospital at {self.city.coords(ph_id)}.")
                    if blocked: self._log(f"  {len(blocked)} blocked road(s) preserved.")
                    self._pending_view = "Road Network"  # switch on next draw (thread-safe)

        except Exception as e:
            import traceback
            self._log(f"Ch3 error: {e}")
            tb = traceback.format_exc()
            for line in tb.strip().splitlines()[-3:]:
                self._log("  " + line.strip())

    # ── Challenge 4 ─────────────────────────────────────────────────
    def _act_emergency(self):
        """
        Context-sensitive Emergency button:
          • No active mission → open CivilianPicker to set up a new mission.
          • Mission active    → advance team one step along current route.
          • Mission complete / blocked → reset so a new mission can be started.
        """
        m = self._em_mission
        if m is None or m.status in ("complete", "no_path"):
            # Setup mode: pick start node and civilians
            self._do_emergency_setup()
        elif m.status == "active":
            # Step mode: advance the team one node
            self._do_em_step()

    def _do_emergency_setup(self):
        """Open CivilianPicker. Start node = first AmbulanceDepot, else Hospital, else any."""
        if not self.city.active_nodes:
            self._log("ERROR: No city loaded."); return
        start = next((n for n in self.city.active_nodes
                      if self.city.assignment.get(n) == "AmbulanceDepot"), None)
        if start is None:
            start = next((n for n in self.city.active_nodes
                          if self.city.assignment.get(n) == "Hospital"), None)
        if start is None:
            start = self.city.active_nodes[0]
        if not self.city.roads:
            self._log("Ch4 note: roads not built — A* uses grid adjacency (hop count).")
        self._em_mission = None
        self._em_picker  = CivilianPicker(self.screen, self.city, start)
        self._set_view("Emergency")
        self._log(f"Ch4: Emergency setup — team starts at {self.city.coords(start)}.")
        self._log("  Click up to 5 nodes as trapped civilians, then Start Mission.")

    def _start_em_mission(self, start, civilians):
        """Create EmergencyMission and log results."""
        import io as _io
        buf = _io.StringIO()
        with redirect_stdout(buf):
            mission = run_challenge4(self.city, start, civilians)
        self._em_mission = mission
        self._em_start   = start
        self.emergency_route = mission.path_ahead

        if mission.status == "active":
            self._log(f"Ch4: Mission started — {len(civilians)} civilian(s) to reach.")
            self._log(f"  Route: {len(mission.route)-1} steps via A* "
                      f"(heuristic: Manhattan × 0.8, admissible).")
            self._log(f"  Press Emergency Setup button to advance step by step.")
            self._log(f"  Block roads with Block Road — re-routing is automatic.")
        elif mission.status == "partial_complete":
            self._log(f"Ch4: Partial mission prepared — {len(mission.skipped)} unreachable civilian(s) skipped.")
            self._log(f"  Reachable civilians will still be handled; reached={len(mission.reached)}/{len(mission.civilians)}.")
        elif mission.status == "no_path":
            self._log("Ch4 ERROR: No A* path found to civilian(s).")
            self._log("  Try building roads (Ch2) or unblocking blocked roads.")
        self._set_view("Emergency")

    def _do_em_step(self):
        """Advance the team one step and handle arrival + re-route detection."""
        m = self._em_mission
        if m is None or m.status != "active":
            return
        if m.at_route_end:
            self._log("Ch4: Team is at the end of the planned route.")
            return

        new_pos, reached = m.advance()
        self.emergency_route = m.path_ahead
        self._log(f"Ch4: Team → {self.city.coords(new_pos)}")

        if reached is not None:
            n_done = len(m.reached); n_total = len(m.civilians)
            self._log(f"  Civilian {n_done}/{n_total} reached at "
                      f"{self.city.coords(reached)}!")
        if m.status == "complete":
            self._log(f"Ch4: MISSION COMPLETE — all {len(m.civilians)} civilians reached.")
            self._log(f"  Total cost: {m.total_cost:.2f}  |  "
                      f"Re-routes triggered: {m.reroutes}")
        elif m.status == "no_path":
            self._log("Ch4: All remaining paths are blocked. Unblock a road to continue.")

    # ── Challenge 5 ─────────────────────────────────────────────────
    def _act_crime_risk(self):
        """Run K-Means + Random Forest crime risk pipeline in background thread."""
        if not self.city.active_nodes:
            self._log("ERROR: No city loaded."); return
        active_count = sum(1 for n in self.city.active_nodes
                           if self.city.assignment.get(n) is not None)
        if active_count < 3:
            self._log(f"ERROR: Need at least 3 active nodes. Have {active_count}.")
            return
        self._log("Ch5: Starting crime risk pipeline...")
        self._set_view("Crime Risk")
        import threading
        threading.Thread(target=self._run_ch5, daemon=True).start()

    def _run_ch5(self):
        """Background thread: full K-Means + RF pipeline."""
        try:
            from challenge5 import run_challenge5

            def cb(msg):
                self._log("  " + str(msg).encode("ascii","replace").decode("ascii"))

            pipeline = run_challenge5(self.city, callback=cb)

            # Build crime_risk dict for GUI heat map: nid -> 0.0..1.0
            crime_risk = {}
            for nid, lbl in pipeline.predictions.items():
                from challenge5 import RISK_VALUES
                crime_risk[nid] = RISK_VALUES[lbl]

            # Atomic GUI update
            self._ch5_pipeline    = pipeline
            self._ch5_deployment  = pipeline.deployment
            self._ch5_predictions = pipeline.predictions
            self._ch5_importances = pipeline.feature_importance
            self.crime_risk       = crime_risk  # triggers Crime Risk view

            counts = {"High":0,"Medium":0,"Low":0}
            for lbl in pipeline.predictions.values():
                counts[lbl] = counts.get(lbl,0)+1

            self._log(f"Ch5 complete: High={counts['High']} "
                      f"Medium={counts['Medium']} Low={counts['Low']}")
            self._log("city.risk_index updated — Ch3 and Ch4 will use new weights.")

            if pipeline.feature_importance:
                imp = pipeline.feature_importance
                best = max(imp, key=lambda k: imp[k])
                self._log(f"Strongest predictor: {best} "
                          f"({imp[best]*100:.1f}% importance)")

        except Exception as e:
            import traceback
            self._log(f"Ch5 error: {e}")
            for line in traceback.format_exc().strip().splitlines()[-3:]:
                self._log("  " + line.strip().encode("ascii","replace").decode("ascii"))

    def _set_view(self,v):
        self.view=v
        for vv,b in self.vbtns: b.active=(vv==v)
        self._log(f"View: {v}")

    # ── Actions ───────────────────────────────────────────────────────
    def _act_add(self): self._open_popup("Add node -- pick type:",self._do_add)

    # ── CHANGE 1: save blocked before add_node wipes city.roads ──────
    def _save_blocked_edges(self):
        blocked=set()
        for node in self.city.active_nodes:
            for nb,edge in self.city.roads.get(node,{}).items():
                if isinstance(edge,dict) and edge.get("blocked",False):
                    blocked.add(frozenset({node,nb}))
        return blocked

    # ── CHANGE 2: rebuild roads after node change, restore blocked ────
    def _auto_rebuild_roads(self,blocked_edges):
        b=self.road_builder
        if b is None:
            self._log("Roads not yet built — click Build Roads to set Primary Hospital first.")
            return
        ph=self.primary_hospital_id
        ph_valid=(ph is not None and self.city.assignment.get(ph)=="Hospital")

        if not ph_valid:
            prev_coords=self.city.coords(ph) if ph is not None else "none"
            hospitals=[n for n in self.city.active_nodes
                       if self.city.assignment.get(n)=="Hospital"]
            if not hospitals:
                self._log("Auto-rebuild skipped: No Hospital on grid."); return
            if len(hospitals)==1:
                new_ph=hospitals[0]
                self._log(f"▶▶ PRIMARY HOSPITAL CHANGED: {prev_coords} → {self.city.coords(new_ph)}")
                ad=next((n for n in self.city.active_nodes
                         if self.city.assignment.get(n)=="AmbulanceDepot"),None)
                if ad is None:
                    self._log("Auto-rebuild skipped: No Ambulance Depot on grid."); return
                b.ambulance_depot=ad
                self._do_auto_rebuild_with_hospital(new_ph,blocked_edges)
            else:
                self._log(f"▶▶ Primary Hospital at {prev_coords} was replaced.")
                self._log(f"   {len(hospitals)} hospital(s) remain — please select a new Primary Hospital.")
                self._picker_blocked_edges=blocked_edges
                self.hospital_picker=HospitalPicker(self.screen,self.city)
            return

        # Primary still valid — rebuild roads with same primary
        ad=next((n for n in self.city.active_nodes
                 if self.city.assignment.get(n)=="AmbulanceDepot"),None)
        if ad is None:
            self._log("Auto-rebuild skipped: No Ambulance Depot on grid."); return
        b.ambulance_depot=ad
        self._do_auto_rebuild_with_hospital(ph,blocked_edges)

    def _do_auto_rebuild_with_hospital(self,ph_nid,blocked_edges):
        """Run full Ch2 pipeline for ph_nid; log MST cost + safety result to GUI."""
        b=self.road_builder
        b.primary_hospital=ph_nid
        buf=io.StringIO()
        with redirect_stdout(buf):
            all_edges=b._get_candidate_edges()
            b._run_kruskals(all_edges)
            b._second_path_augmentation()
            b._write_to_city_graph(blocked_edges=blocked_edges)
            safe,failing=b._verify_safety()
        self.primary_hospital_id=ph_nid
        mst_cost=sum(co for _,_,co in b.mst_edges)
        self._log(f"Roads rebuilt — Primary Hospital: {self.city.coords(ph_nid)}.")
        self._log(f"  MST cost={mst_cost:.1f}, backup edges={len(b.backup_edges)}")
        if blocked_edges:
            self._log(f"  {len(blocked_edges)} blocked road(s) preserved.")
        if safe:
            self._log("  ✅ Safety guaranteed: two independent Hospital↔Depot routes confirmed.")
        else:
            self._log("  ⚠ SAFETY NOT GUARANTEED — two independent routes could not be established.")
            for msg in failing:
                self._log(f"    {msg}")
            suggestions=self._find_unblocking_suggestions(ph_nid,b.ambulance_depot,blocked_edges)
            if suggestions:
                self._log("  Unblocking any of these roads may restore the safety guarantee:")
                for u,v in suggestions[:3]:
                    self._log(f"    → Select {self.city.coords(u)} or {self.city.coords(v)}, then click Block Road")
            else:
                self._log("  Grid may be too sparse to support two independent routes.")
        self._set_view("Road Network")

    def _find_unblocking_suggestions(self,ph,ad,blocked_edges):
        """Return up to 3 (u,v) pairs from blocked_edges that, if unblocked, restore safety."""
        if not blocked_edges or self.road_builder is None:
            return []
        suggestions=[]
        for key in blocked_edges:
            u,v=tuple(key)
            for a,bb in [(u,v),(v,u)]:
                if bb in self.city.roads.get(a,{}):
                    self.city.roads[a][bb]["blocked"]=False
            buf=io.StringIO()
            with redirect_stdout(buf):
                safe,_=self.road_builder._verify_safety()
            if safe:
                suggestions.append((u,v))
            for a,bb in [(u,v),(v,u)]:
                if bb in self.city.roads.get(a,{}):
                    self.city.roads[a][bb]["blocked"]=True
            if len(suggestions)==3:
                break
        return suggestions

    # ── CHANGE 3: _do_add — save blocked first, auto-rebuild if roads exist
    def _do_add(self,t):
        if t not in LOCATION_TYPES: return
        blocked=self._save_blocked_edges()
        buf=io.StringIO()
        with redirect_stdout(buf): self.manager.add_node(t)
        self._log(f"Added: {t}")
        if self.road_builder is not None: self._auto_rebuild_roads(blocked)
        self.ambulance_nodes=[]; self._amb_coverage={}
        self._ga_worst=None; self._ga_gens=None
        # Clear Ch5 results too — grid changed
        self.crime_risk={}; self._ch5_predictions={}
        self._ch5_deployment={}; self._ch5_importances={}

    def _act_replace(self):
        if not self.selected: self._log("Click a cell first, then Replace Node"); return
        self._open_popup("Replace -- pick new type:",self._do_replace)

    # ── CHANGE 4: _do_replace — save blocked first, auto-rebuild if roads exist
    def _do_replace(self,t):
        if not self.selected or t not in LOCATION_TYPES: return
        r,c=self.selected; nid=self.city.node_id(r,c)
        blocked=self._save_blocked_edges()
        buf=io.StringIO()
        with redirect_stdout(buf): self.manager.replace_node(nid,t)
        self._log(f"Replaced ({r},{c}) -> {t}")
        if self.road_builder is not None: self._auto_rebuild_roads(blocked)
        self.ambulance_nodes=[]; self._amb_coverage={}
        self._ga_worst=None; self._ga_gens=None
        # Clear Ch5 results too — grid changed
        self.crime_risk={}; self._ch5_predictions={}
        self._ch5_deployment={}; self._ch5_importances={}

    def _act_build_roads(self):
        has_h=any(self.city.assignment.get(n)=="Hospital" for n in self.city.active_nodes)
        has_d=any(self.city.assignment.get(n)=="AmbulanceDepot" for n in self.city.active_nodes)
        if not has_h: self._log("No Hospital found."); return
        if not has_d: self._log("No Ambulance Depot found."); return
        self._log("Click a HOSPITAL cell to designate it as Primary Hospital...")
        self.hospital_picker=HospitalPicker(self.screen,self.city)

    # ── CHANGE 5: pass blocked_edges=None so city.roads is harvested before overwrite
    def _do_build_roads(self,ph_nid):
        buf=io.StringIO()
        with redirect_stdout(buf):
            builder=RoadNetworkBuilder(self.city)
            builder.primary_hospital=ph_nid
            for nid in self.city.active_nodes:
                if self.city.assignment.get(nid)=="AmbulanceDepot":
                    builder.ambulance_depot=nid; break
            if builder.ambulance_depot is None: self._log("No Depot found."); return
            all_edges=builder._get_candidate_edges()
            builder._run_kruskals(all_edges)
            builder._second_path_augmentation()
            builder._write_to_city_graph(blocked_edges=None)
            builder.display()
            safe,failing=builder._verify_safety()
        self.road_builder=builder
        self.primary_hospital_id=ph_nid
        mst_cost=sum(co for _,_,co in builder.mst_edges)
        self._log(f"Roads built — Primary Hospital at {self.city.coords(ph_nid)}.")
        self._log(f"MST cost={mst_cost:.1f}, backup edges={len(builder.backup_edges)}")
        if safe:
            self._log("✅ Safety: two independent Hospital↔Depot routes confirmed.")
        else:
            self._log("⚠ Safety NOT guaranteed:")
            for msg in failing:
                self._log(f"  {msg}")
        self._set_view("Road Network")

    def _act_block_road(self):
        if not self.selected: self._log("Select a cell first, then Block Road"); return
        r,c=self.selected; nid=self.city.node_id(r,c)
        if nid in self.city.roads:
            for nb,data in self.city.roads[nid].items():
                if isinstance(data,dict):
                    data["blocked"]=not data.get("blocked",False)
                    self.city.roads[nb][nid]["blocked"]=data["blocked"]
            self._log(f"Toggled road block on ({r},{c}) neighbours.")
            # Ch4: if an emergency mission is active, check if re-route is needed
            m=self._em_mission
            if m is not None and m.status=="active":
                if m.check_reroute():
                    self.emergency_route=m.path_ahead
                    if getattr(m, "last_skipped", []):
                        coords=", ".join(str(self.city.coords(x)) for x in m.last_skipped)
                        self._log(f"Ch4: Unreachable civilian(s) skipped: {coords}")
                        self._log("  Mission continues toward remaining reachable civilians.")
                    self._log(f"Ch4: Road change detected — A* re-routed immediately.")
                    self._log(f"  Re-routes so far: {m.reroutes}  |  "
                              f"New route: {max(0, len(m.path_ahead)-1)} steps.")
                    if m.status=="partial_complete":
                        self._log(f"Ch4: Reachable-civilian mission complete; skipped={len(m.skipped)}.")
                    elif m.status=="no_path":
                        self._log("Ch4: WARNING — no path available to remaining civilians.")
            # Primary hospital isolation check
            if self.road_builder is not None and self.primary_hospital_id is not None:
                ph=self.primary_hospital_id
                ph_roads=self.city.roads.get(ph,{})
                all_blocked=(not ph_roads or all(
                    isinstance(data,dict) and data.get("blocked",False)
                    for data in ph_roads.values()
                ))
                if all_blocked:
                    self._log(f"ERROR: Primary Hospital at {self.city.coords(ph)} is completely isolated — all connecting roads are blocked!")
                    self._log("  Select a new Primary Hospital to rebuild the road network.")
                    self.hospital_picker=HospitalPicker(self.screen,self.city)
        else: self._log("No roads found. Build roads first.")

    def _act_validate(self):
        ok,viols=self.manager.checker.full_check(self.city.assignment,self.city.active_nodes)
        if ok: self._log("Validation: all constraints satisfied")
        else:
            self._log(f"Validation: {len(viols)} violation(s) found")
            self.violation_panel=ViolationPanel(self.screen,self.manager,viols)

    # ── Type picker popup ──────────────────────────────────────────────
    def _open_popup(self,title,cb):
        W,H=self.screen.get_size()
        pw=360; bh=42; gap=6
        ph=60+len(LOCATION_TYPES)*(bh+gap)+14
        px=W//2-pw//2; py=H//2-ph//2; btns=[]
        for t in LOCATION_TYPES:
            base=C.get(t,C["btn"])
            b=Button((px+16,py+48+len(btns)*(bh+gap),pw-32,bh),
                     f"{SHORT[t]}  --  {t}",color=base,
                     hcolor=tuple(min(255,v+30) for v in base),tcolor=(240,240,240))
            btns.append((t,b))
        self.popup={"title":title,"rect":(px,py,pw,ph),"btns":btns,"cb":cb}

    def _popup_ev(self,ev,pos):
        p=self.popup
        if ev.type==pygame.MOUSEBUTTONDOWN:
            if not pygame.Rect(p["rect"]).collidepoint(pos): self.popup=None; return
        for t,btn in p["btns"]:
            btn.update(pos)
            if btn.hit(pos,ev): p["cb"](t); self.popup=None; return


    # ── System Integration Simulation ────────────────────────────────
    def _act_integration_sim(self):
        """Prepare the required 20-step scenario, then wait for manual stepping."""
        if self._sim_running or self._sim_auto_running:
            self._log("SIM is busy — wait for the current step to finish.")
            return
        if not self.city.active_nodes:
            self._log("ERROR: No city loaded.")
            return
        self._set_view("Emergency")
        self._log("SIM: Preparing step-controlled 20-step simulation...")
        self._sim_running=True
        threading.Thread(target=self._prepare_integration_sim_thread, daemon=True).start()

    def _prepare_integration_sim_thread(self):
        try:
            from integration_simulation import create_integration_simulation
            self._sim_controller = create_integration_simulation(
                self.city,
                gui=self,
                steps=20,
                seed=None,
                log=self._log,
            )
            self._sim_state = self._sim_controller.prepare()
            self._log("SIM: Manual controls enabled — use Next Sim Step or Auto Slow Sim.")
        except Exception as e:
            import traceback
            self._log(f"SIM error: {e}")
            for line in traceback.format_exc().strip().splitlines()[-4:]:
                self._log("  " + line.strip().encode("ascii", "replace").decode("ascii"))
        finally:
            self._sim_running=False

    def _act_next_sim_step(self):
        """Run exactly one visible simulation step, then pause."""
        if self._sim_running:
            self._log("SIM step already running — wait for it to finish.")
            return
        if self._sim_controller is None:
            self._log("SIM not prepared yet — click Start Step Sim first.")
            return
        if self._sim_state and getattr(self._sim_state, "steps_completed", 0) >= 20:
            self._log("SIM already completed all 20 steps.")
            return
        self._sim_running=True
        self._set_view("Emergency")
        threading.Thread(target=self._run_one_sim_step_thread, daemon=True).start()

    def _run_one_sim_step_thread(self):
        try:
            self._sim_state = self._sim_controller.step_once()
        except Exception as e:
            import traceback
            self._log(f"SIM step error: {e}")
            for line in traceback.format_exc().strip().splitlines()[-4:]:
                self._log("  " + line.strip().encode("ascii", "replace").decode("ascii"))
        finally:
            self._sim_running=False

    def _act_auto_slow_sim(self):
        """Run remaining steps automatically, pausing ~6 seconds after each one."""
        if self._sim_auto_running:
            self._log("SIM auto mode already running.")
            return
        if self._sim_running:
            self._log("SIM step already running — wait for it to finish.")
            return
        if self._sim_controller is None:
            self._log("SIM not prepared yet — click Start Step Sim first.")
            return
        if self._sim_state and getattr(self._sim_state, "steps_completed", 0) >= 20:
            self._log("SIM already completed all 20 steps.")
            return
        self._sim_auto_running=True
        self._set_view("Emergency")
        self._log("SIM AUTO: running slowly — about 6 seconds per step.")
        threading.Thread(target=self._run_auto_slow_sim_thread, daemon=True).start()

    def _run_auto_slow_sim_thread(self):
        try:
            while self._sim_controller is not None:
                if self._sim_state and getattr(self._sim_state, "steps_completed", 0) >= 20:
                    break
                self._sim_running=True
                self._sim_state = self._sim_controller.step_once()
                self._sim_running=False
                if getattr(self._sim_state, "steps_completed", 0) >= 20:
                    break
                time.sleep(6)  # user asked for roughly 5-7 seconds per simulation step
            self._log("SIM AUTO: stopped.")
        except Exception as e:
            import traceback
            self._log(f"SIM auto error: {e}")
            for line in traceback.format_exc().strip().splitlines()[-4:]:
                self._log("  " + line.strip().encode("ascii", "replace").decode("ascii"))
        finally:
            self._sim_running=False
            self._sim_auto_running=False

    # ── Draw ─────────────────────────────────────────────────────────
    def draw(self):
        W,H=self.screen.get_size()
        # Keep simulation button labels/state visible during step-controlled simulation
        for b, cb in self.abtns:
            if cb is self._act_integration_sim:
                b.label = "Preparing..." if self._sim_running and self._sim_controller is None else "Start Step Sim"
            elif cb is self._act_next_sim_step:
                step = getattr(self._sim_state, "steps_completed", 0) if self._sim_state else 0
                b.label = "Step Running..." if self._sim_running and self._sim_controller is not None else f"Next Sim Step ({step}/20)"
            elif cb is self._act_auto_slow_sim:
                b.label = "Auto Running..." if self._sim_auto_running else "Auto Slow Sim"
        # Apply view switch requested by background threads (e.g. after GA + road rebuild)
        if self._pending_view:
            self._set_view(self._pending_view); self._pending_view=None
        # Update Emergency button label to reflect mission state
        if self._em_btn:
            m=self._em_mission
            if m and m.status=="active" and not m.at_route_end:
                self._em_btn.label="Step Mission  ▶"
            elif m and m.status=="complete":
                self._em_btn.label="New Mission"
            elif m and m.status=="no_path":
                self._em_btn.label="Retry Mission"
            else:
                self._em_btn.label="Emergency Setup"
        self.screen.fill(C["bg"])
        self._draw_background_glow()
        self._draw_topbar()
        self._draw_sidebar()
        self._draw_right_panel()
        self._draw_grid()
        self._draw_bottom_area()
        if self.popup: self._draw_popup()
        if self.violation_panel and not self.violation_panel.done:
            self.violation_panel.draw()
        if self.hospital_picker and not self.hospital_picker.done:
            self.hospital_picker.draw()
        if self._em_picker and not self._em_picker.done:
            self._em_picker.draw()
        pygame.display.flip()

    def _draw_background_glow(self):
        """Dramatic multi-layer radial glows for a neon city dashboard feel."""
        W, H = self.screen.get_size()
        t_ms = pygame.time.get_ticks()
        import math
        pulse = 0.5 + 0.5 * math.sin(t_ms / 2000)
        for cx, cy, r, col, base_alpha in [
            (int(W * 0.38), int(H * 0.08), 280, C["accent"],  22),
            (int(W * 0.82), int(H * 0.30), 320, C["accent3"], 16),
            (int(W * 0.55), int(H * 0.92), 300, C["accent2"], 12),
            (int(W * 0.15), int(H * 0.60), 200, C["accent"],  10),
        ]:
            alpha = int(base_alpha * (0.8 + 0.2 * pulse))
            surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            for rr in range(r, 0, -14):
                a = max(0, int(alpha * (rr / r) ** 1.6))
                pygame.draw.circle(surf, (*col, a), (r, r), rr)
            self.screen.blit(surf, (cx - r, cy - r))

    def _draw_right_panel(self):
        """Wide-screen inspector: metrics, legend, mission and sim status.

        This keeps the left sidebar clean and prevents long info blocks from
        overflowing the command rail. Hidden automatically on narrow windows.
        """
        W,H=self.screen.get_size()
        rw=get_right_panel_width(self.screen)
        if not rw:
            return
        font,sf,bf,tiny=make_fonts(H)
        x=W-rw+10; y=92; w=rw-20
        panel=pygame.Rect(W-rw,0,rw,H)
        pygame.draw.rect(self.screen,(8,13,30),panel)
        pygame.draw.line(self.screen,(49,64,104),(panel.x,0),(panel.x,H),1)

        # Header card
        head=pygame.Rect(x,12,w,64)
        draw_card(self.screen,head,fill=(16,25,52),border=(54,73,118),radius=18,shadow=True)
        self.screen.blit(sf.render("INTELLIGENCE PANEL",True,C["muted"]),(head.x+16,head.y+12))
        view_txt=bf.render(self.view,True,C["text"])
        while view_txt.get_width()>head.w-32 and len(self.view)>4:
            break
        self.screen.blit(view_txt,(head.x+16,head.y+30))

        y=self._draw_metrics_card(x,y,w,sf,tiny)
        y=self._draw_context_legend_card(x,y+12,w,sf,tiny)
        y=self._draw_sim_status_card(x,y+12,w,sf,tiny)
        self._draw_mission_card(x,y+12,w,sf,tiny)

    def _draw_metrics_card(self,x,y,w,sf,tiny):
        city=self.city
        road_count=sum(len(v) for v in city.roads.values())//2 if city.roads else 0
        blocked=sum(1 for u in city.roads for e in city.roads[u].values() if isinstance(e,dict) and e.get("blocked"))//2 if city.roads else 0
        active=len(city.active_nodes)
        risks=getattr(self,"crime_risk",{}) or {}
        high=sum(1 for v in getattr(self,"_ch5_predictions",{}).values() if v=="High")
        card=pygame.Rect(x,y,w,156)
        draw_card(self.screen,card,fill=(15,23,48),border=(48,65,108),radius=18,shadow=True)
        self.screen.blit(sf.render("CITY METRICS",True,C["muted"]),(card.x+16,card.y+14))
        metrics=[("Nodes",active,C["accent"]),("Roads",road_count,C["road_mst"]),("Blocked",blocked,C["danger"]),("High Risk",high,C["warn"])]
        col_w=(card.w-32)//2
        for i,(label,val,col) in enumerate(metrics):
            cx=card.x+16+(i%2)*col_w; cy=card.y+44+(i//2)*48
            pygame.draw.circle(self.screen,col,(cx+7,cy+10),6)
            self.screen.blit(tiny.render(label.upper(),True,C["muted"]),(cx+20,cy))
            self.screen.blit(sf.render(str(val),True,C["text"]),(cx+20,cy+17))
        return card.bottom

    def _draw_context_legend_card(self,x,y,w,sf,tiny):
        card=pygame.Rect(x,y,w,196)
        draw_card(self.screen,card,fill=(15,23,48),border=(48,65,108),radius=18,shadow=True)
        self.screen.blit(sf.render("VIEW LEGEND",True,C["muted"]),(card.x+16,card.y+14))
        yy=card.y+44; lx=card.x+18; line=24
        view=self.view
        if view=="City Layout":
            items=[(C[t],f"{SHORT[t]}  {t}") for t in LOCATION_TYPES]
            for col,txt in items[:6]:
                pygame.draw.rect(self.screen,col,(lx,yy+5,14,14),border_radius=4)
                self.screen.blit(tiny.render(txt,True,C["text_dim"]),(lx+24,yy+2)); yy+=line
        elif view=="Road Network":
            items=[(C["road_mst"],"MST optimal road"),(C["road_backup"],"Backup safety route"),(C["road_other"],"Other adjacency"),(C["road_blocked"],"Flooded / blocked")]
            for col,txt in items:
                pygame.draw.rect(self.screen,col,(lx,yy+9,30,5),border_radius=4)
                self.screen.blit(tiny.render(txt,True,C["text_dim"]),(lx+42,yy+1)); yy+=line
        elif view=="Ambulance":
            items=[(C["accent2"],"GA selected depot"),(C["warn"],"Farther coverage"),(C["accent"],"Closer coverage")]
            for col,txt in items:
                pygame.draw.circle(self.screen,col,(lx+8,yy+11),7)
                self.screen.blit(tiny.render(txt,True,C["text_dim"]),(lx+24,yy+2)); yy+=line
            if getattr(self,"_ga_worst",None) is not None:
                self.screen.blit(tiny.render(f"Worst case: {self._ga_worst:.2f}",True,C["accent2"]),(lx,yy+4))
        elif view=="Emergency":
            items=[(C["danger"],"A* route ahead"),(C["warn"],"Civilian remaining"),(C["accent2"],"Reached / safe")]
            for col,txt in items:
                pygame.draw.circle(self.screen,col,(lx+8,yy+11),7)
                self.screen.blit(tiny.render(txt,True,C["text_dim"]),(lx+24,yy+2)); yy+=line
            self.screen.blit(tiny.render("Reroutes happen immediately",True,C["warn"]),(lx,yy+6))
        elif view=="Crime Risk":
            for lbl,col in [("Low",(40,180,80)),("Medium",(230,180,50)),("High",C["danger"])]:
                pygame.draw.rect(self.screen,col,(lx,yy+5,14,14),border_radius=4)
                self.screen.blit(tiny.render(lbl,True,C["text_dim"]),(lx+24,yy+2)); yy+=line
            imp=getattr(self,"_ch5_importances",{})
            if imp:
                best=max(imp,key=lambda k:imp[k])
                self.screen.blit(tiny.render(f"Top factor: {best}",True,C["accent2"]),(lx,yy+4))
        return card.bottom

    def _draw_sim_status_card(self,x,y,w,sf,tiny):
        card=pygame.Rect(x,y,w,128)
        draw_card(self.screen,card,fill=(16,28,58),border=(58,82,142),radius=18,shadow=True)
        self.screen.blit(sf.render("20-STEP SIMULATION",True,C["muted"]),(card.x+16,card.y+14))
        step=getattr(self._sim_state,"steps_completed",0) if self._sim_state else 0
        status="Auto running" if self._sim_auto_running else "Step running" if self._sim_running else "Ready" if self._sim_controller else "Not started"
        self.screen.blit(sf.render(f"Step {step}/20",True,C["text"]),(card.x+16,card.y+46))
        # progress bar
        bar=pygame.Rect(card.x+16,card.y+78,card.w-32,10)
        pygame.draw.rect(self.screen,(34,47,82),bar,border_radius=6)
        fill_w=int(bar.w*(step/20)) if step else 0
        if fill_w:
            pygame.draw.rect(self.screen,C["accent2"],pygame.Rect(bar.x,bar.y,fill_w,bar.h),border_radius=6)
        self.screen.blit(tiny.render(status,True,C["text_dim"]),(card.x+16,card.y+96))
        return card.bottom

    def _draw_mission_card(self,x,y,w,sf,tiny):
        card=pygame.Rect(x,y,w,150)
        draw_card(self.screen,card,fill=(15,23,48),border=(48,65,108),radius=18,shadow=True)
        self.screen.blit(sf.render("EMERGENCY ROUTING",True,C["muted"]),(card.x+16,card.y+14))
        m=self._em_mission
        if m:
            rows=[("Status",m.status),("Civilians",f"{len(m.reached)}/{len(m.civilians)}"),("Reroutes",str(m.reroutes)),("Cost",f"{m.total_cost:.2f}")]
        else:
            rows=[("Status","No active mission"),("Route","Not planned"),("Reroutes","0"),("Cost","0.00")]
        yy=card.y+44
        for label,val in rows:
            self.screen.blit(tiny.render(label.upper(),True,C["muted"]),(card.x+16,yy))
            txt=sf.render(str(val),True,C["text"] if label!="Reroutes" else C["warn"])
            self.screen.blit(txt,(card.right-txt.get_width()-16,yy-3))
            yy+=24
        return card.bottom

    def _draw_topbar(self):
        import math
        W, H = self.screen.get_size()
        _, _, sw, th, _, _, _, _, _ = get_dims(self.screen)
        font, sf, bf, tiny = make_fonts(H)
        rw = get_right_panel_width(self.screen)
        bar = pygame.Rect(sw + 8, 6, W - sw - rw - 16, th - 10)
        # Glassmorphism card with neon border
        draw_card(self.screen, bar, fill=(14, 20, 44), border=(64, 96, 200), radius=16, shadow=True)
        # Animated neon accent dot
        t_ms = pygame.time.get_ticks()
        pulse = 0.5 + 0.5 * math.sin(t_ms / 700)
        glow_r = int(10 + 4 * pulse)
        glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*C["accent"], 60), (glow_r + 2, glow_r + 2), glow_r + 2)
        cx_dot = bar.x + 26; cy_dot = bar.centery
        self.screen.blit(glow_surf, (cx_dot - glow_r - 2, cy_dot - glow_r - 2))
        pygame.draw.circle(self.screen, C["accent3"], (cx_dot, cy_dot), 9)
        pygame.draw.circle(self.screen, C["accent2"], (cx_dot, cy_dot), 4)
        # Title
        t = bf.render("CityMind", True, C["text"])
        self.screen.blit(t, (bar.x + 46, bar.centery - t.get_height() // 2 - 1))
        # Separator
        sep_x = bar.x + 46 + t.get_width() + 14
        pygame.draw.line(self.screen, (55, 72, 120), (sep_x, bar.y + 12), (sep_x, bar.bottom - 12), 1)
        # View chip
        chip_lbl = sf.render(self.view, True, C["accent"])
        chip_rect = pygame.Rect(sep_x + 12, bar.centery - chip_lbl.get_height() // 2 - 3,
                                chip_lbl.get_width() + 20, chip_lbl.get_height() + 6)
        pygame.draw.rect(self.screen, (24, 38, 78), chip_rect, border_radius=8)
        pygame.draw.rect(self.screen, C["accent"], chip_rect, 1, border_radius=8)
        self.screen.blit(chip_lbl, (chip_rect.x + 10, chip_rect.y + 3))
        # Right-side info
        info = (f"{self.city.rows}×{self.city.cols} grid  •  "
                f"{len(self.city.active_nodes)} nodes  •  "
                f"{'Roads built' if self.city.roads else 'No roads'}")
        v = sf.render(info, True, C["text_dim"])
        self.screen.blit(v, (bar.right - v.get_width() - 18, bar.centery - v.get_height() // 2))

    def _draw_section_header(self, label, x, y, w, sf):
        """Pill-style section header with accent left-bar."""
        pygame.draw.rect(self.screen, (22, 32, 64), pygame.Rect(x, y, w, 20), border_radius=6)
        pygame.draw.rect(self.screen, C["accent"], pygame.Rect(x, y + 3, 3, 14), border_radius=2)
        self.screen.blit(sf.render(label, True, C["muted"]), (x + 10, y + 2))

    def _draw_sidebar(self):
        import math
        W, H = self.screen.get_size()
        _, _, sw, th, lh, _, _, _, _ = get_dims(self.screen)
        font, sf, bf, tiny = make_fonts(H)

        # Background with subtle gradient feel
        pygame.draw.rect(self.screen, C["sidebar"], (0, 0, sw, H))
        # Edge glow
        glow_surf = pygame.Surface((4, H), pygame.SRCALPHA)
        for i in range(4):
            pygame.draw.line(glow_surf, (*C["accent"], max(0, 60 - i * 20)), (3 - i, 0), (3 - i, H))
        self.screen.blit(glow_surf, (sw - 4, 0))
        pygame.draw.line(self.screen, (7, 10, 22), (sw, 0), (sw, H), 2)

        # Animated brand area
        t_ms = pygame.time.get_ticks()
        pulse = 0.5 + 0.5 * math.sin(t_ms / 800)
        brand = pygame.Rect(10, 8, sw - 20, max(48, th - 14))
        draw_card(self.screen, brand, fill=(16, 25, 54), border=(60, 88, 160), radius=14, shadow=True)
        # Pulsing ring behind logo dot
        ring_r = int(13 + 4 * pulse)
        ring_surf = pygame.Surface((ring_r * 2 + 2, ring_r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(ring_surf, (*C["accent3"], int(40 * pulse)), (ring_r + 1, ring_r + 1), ring_r)
        cx_b = brand.x + 22; cy_b = brand.centery
        self.screen.blit(ring_surf, (cx_b - ring_r - 1, cy_b - ring_r - 1))
        pygame.draw.circle(self.screen, C["accent3"], (cx_b, cy_b), 10)
        pygame.draw.circle(self.screen, C["accent2"], (cx_b, cy_b), 5)
        pygame.draw.circle(self.screen, (255, 255, 255), (cx_b, cy_b), 2)
        self.screen.blit(bf.render("CityMind", True, C["text"]), (brand.x + 40, brand.y + 8))
        if brand.h > 46:
            self.screen.blit(tiny.render("AI City Operations", True, C["text_dim"]),
                             (brand.x + 42, brand.y + 32))

        body_clip = pygame.Rect(0, th, sw, H - th)
        self.screen.set_clip(body_clip)
        scroll = int(getattr(self, "sidebar_scroll", 0))
        section_y = th + 14 - scroll

        # ── NAVIGATION ─────────────────────────────────────────
        self._draw_section_header("NAVIGATION", 10, section_y, sw - 20, sf)
        for _, b in self.vbtns:
            b.draw(self.screen, font)

        # ── MANAGEMENT ─────────────────────────────────────────
        if self.abtns:
            first_act_y = self.abtns[0][0].rect.top - 20
            self._draw_section_header("MANAGEMENT", 10, first_act_y, sw - 20, sf)
            for btn, _ in self.abtns[:8]:
                btn.draw(self.screen, font)

        # ── SIMULATION ─────────────────────────────────────────
        if len(self.abtns) >= 9:
            first_sim_y = self.abtns[8][0].rect.top - 20
            self._draw_section_header("SIMULATION", 10, first_sim_y, sw - 20, sf)
            for btn, _ in self.abtns[8:]:
                btn.draw(self.screen, font)

        last_bottom = max([b.rect.bottom for b, _ in self.abtns] or [section_y + 40])
        if not get_right_panel_width(self.screen):
            self._draw_sidebar_stats(sw, last_bottom + 16, sf, tiny)
            self._draw_sidebar_legend_card(sw, last_bottom + 210, sf, tiny)
        self.screen.set_clip(None)

        # Scrollbar
        visible_h = max(1, H - th - 10)
        max_scroll = max(0, getattr(self, "_sidebar_content_bottom", H) - (th + visible_h))
        if max_scroll > 0:
            track = pygame.Rect(sw - 8, th + 8, 4, H - th - 18)
            pygame.draw.rect(self.screen, (36, 48, 80), track, border_radius=4)
            thumb_h = max(32, int(track.h * visible_h / max(visible_h + max_scroll, 1)))
            frac = getattr(self, "sidebar_scroll", 0) / max_scroll
            thumb_y = track.y + int((track.h - thumb_h) * frac)
            pygame.draw.rect(self.screen, C["accent"],
                             pygame.Rect(track.x, thumb_y, track.w, thumb_h), border_radius=4)

    def _draw_sidebar_stats(self,sw,y,sf,tiny):
        card=pygame.Rect(12,y,sw-24,174)
        draw_card(self.screen,card,fill=(15,23,48),border=(46,62,104),radius=14,shadow=False)
        self.screen.blit(sf.render("LIVE SUMMARY",True,C["muted"]),(card.x+12,card.y+10))
        counts=Counter(self.city.assignment.get(n) for n in self.city.active_nodes if self.city.assignment.get(n))
        left=card.x+14; yy=card.y+34
        rows=[("Nodes",str(len(self.city.active_nodes)),C["accent"]),
              ("Roads",str(sum(len(v) for v in self.city.roads.values())//2 if self.city.roads else 0),C["road_mst"]),
              ("Blocked",str(sum(1 for u in self.city.roads for e in self.city.roads[u].values() if isinstance(e,dict) and e.get("blocked"))//2 if self.city.roads else 0),C["danger"]),
              ("Ambulances",str(len(self.ambulance_nodes)),C["accent2"])]
        for label,val,col in rows:
            pygame.draw.circle(self.screen,col,(left+5,yy+8),5)
            self.screen.blit(tiny.render(label,True,C["text_dim"]),(left+18,yy))
            rv=sf.render(val,True,C["text"]) if False else sf.render(val,True,C["text"])
            self.screen.blit(rv,(card.right-rv.get_width()-14,yy-1))
            yy+=24
        yy+=4
        # Mini node type strip
        strip_w=max(10,card.w-28)
        x=left
        total=max(1,sum(counts.values()))
        for t in LOCATION_TYPES:
            w=max(2,int(strip_w*counts.get(t,0)/total))
            pygame.draw.rect(self.screen,C.get(t,C["muted"]),pygame.Rect(x,yy,w,8),border_radius=3)
            x+=w
        self.screen.blit(tiny.render("Type distribution",True,C["muted"]),(left,yy+13))

    def _draw_sidebar_legend_card(self,sw,y,sf,tiny):
        card=pygame.Rect(12,y,sw-24,152)
        draw_card(self.screen,card,fill=(15,23,48),border=(46,62,104),radius=14,shadow=False)
        self.screen.blit(sf.render("LEGEND",True,C["muted"]),(card.x+12,card.y+10))
        lx=card.x+14; yy=card.y+36; line=20
        view=self.view
        if view=="City Layout":
            items=[(C[t],SHORT[t]) for t in LOCATION_TYPES[:5]]
            for col,txt in items:
                pygame.draw.rect(self.screen,col,(lx,yy+4,12,12),border_radius=3)
                self.screen.blit(tiny.render(txt,True,C["text_dim"]),(lx+18,yy+1)); yy+=line
        elif view=="Road Network":
            items=[(C["road_mst"],"MST"),(C["road_backup"],"Backup"),(C["road_other"],"Other"),(C["road_blocked"],"Blocked")]
            for col,txt in items:
                pygame.draw.rect(self.screen,col,(lx,yy+7,24,4),border_radius=3)
                self.screen.blit(tiny.render(txt,True,C["text_dim"]),(lx+34,yy)); yy+=line
        elif view=="Ambulance":
            pygame.draw.circle(self.screen,C["accent2"],(lx+8,yy+8),8,2)
            self.screen.blit(tiny.render("GA ambulance node",True,C["text_dim"]),(lx+24,yy)); yy+=line
            worst=getattr(self,"_ga_worst",None)
            if worst is not None:
                self.screen.blit(tiny.render(f"Worst-case: {worst:.1f}",True,C["accent2"]),(lx,yy)); yy+=line
        elif view=="Emergency":
            pygame.draw.rect(self.screen,C["danger"],(lx,yy+7,24,4),border_radius=3)
            self.screen.blit(tiny.render("A* route",True,C["text_dim"]),(lx+34,yy)); yy+=line
            m=self._em_mission
            if m:
                self.screen.blit(tiny.render(f"Status: {m.status}",True,C["warn"]),(lx,yy)); yy+=line
                self.screen.blit(tiny.render(f"Reached: {len(m.reached)}/{len(m.civilians)}",True,C["text_dim"]),(lx,yy)); yy+=line
        elif view=="Crime Risk":
            for lbl,col in [("Low",(40,180,80)),("Med",(230,180,50)),("High",C["danger"] )]:
                pygame.draw.rect(self.screen,col,(lx,yy+4,12,12),border_radius=3)
                self.screen.blit(tiny.render(lbl,True,C["text_dim"]),(lx+18,yy)); yy+=line
            preds=getattr(self,"_ch5_predictions",{})
            if preds:
                counts={"High":0,"Medium":0,"Low":0}
                for l in preds.values(): counts[l]=counts.get(l,0)+1
                self.screen.blit(tiny.render(f"H:{counts['High']} M:{counts['Medium']} L:{counts['Low']}",True,C["accent2"]),(lx,yy))


    # ── Grid ──────────────────────────────────────────────────────────
    def _draw_grid(self):
        W, H = self.screen.get_size()
        _, _, sw, th, lh, gx, gy, gw, gh = get_dims(self.screen)
        LEGEND_BAR_H = 36
        canvas = pygame.Rect(gx + 10, gy + 10, gw - 20, gh - 20)
        draw_card(self.screen, canvas, fill=C["grid_bg"], border=(42, 56, 94), radius=18, shadow=True)
        city = self.city
        if not city.active_nodes:
            return
        self.screen.set_clip(canvas)
        ox, oy, sz = self._geom()
        m = CELL_MARGIN
        view = self.view
        font, sf, _, tiny = make_fonts(H)

        self._draw_roads(ox, oy, sz, view, tiny)

        for r in range(city.rows):
            for c in range(city.cols):
                nid = city.node_id(r, c)
                loc = city.assignment.get(nid)
                rect = pygame.Rect(ox + c * sz + m, oy + r * sz + m, sz - m * 2, sz - m * 2)
                if rect.right < canvas.left or rect.left > canvas.right:
                    continue
                if rect.bottom < canvas.top or rect.top > canvas.bottom:
                    continue

                if view == "Crime Risk" and nid in self.crime_risk:
                    risk = self.crime_risk[nid]
                    if risk <= 0.2:
                        col = (40, 180, 40)
                    elif risk <= 0.5:
                        col = (220, 180, 38)
                    else:
                        col = (210, 58, 58)
                else:
                    col = C.get(loc, C[None])

                # 3D node rendering
                draw_node_3d(self.screen, rect, col, border_radius=8)

                # Primary hospital gold border
                if (self.road_builder and self.primary_hospital_id is not None
                        and nid == self.primary_hospital_id):
                    pygame.draw.rect(self.screen, (255, 215, 0), rect, 3, border_radius=8)

                if self.selected == (r, c):
                    sel_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                    pygame.draw.rect(sel_surf, (255, 255, 255, 60),
                                     pygame.Rect(0, 0, rect.w, rect.h), border_radius=8)
                    pygame.draw.rect(sel_surf, (255, 255, 255, 200),
                                     pygame.Rect(0, 0, rect.w, rect.h), 2, border_radius=8)
                    self.screen.blit(sel_surf, rect.topleft)

                if view == "Ambulance":
                    cov = getattr(self, "_amb_coverage", {})
                    worst = getattr(self, "_ga_worst", 1) or 1
                    if nid in cov:
                        frac = min(1.0, cov[nid] / worst)
                        heat = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                        rc = int(frac * 180); gc = int((1 - frac) * 160)
                        heat.fill((rc, gc, 20, 90))
                        self.screen.blit(heat, rect.topleft)
                    if nid in self.ambulance_nodes:
                        pygame.draw.rect(self.screen, C["accent2"], rect, 3, border_radius=8)

                if sz >= 40 and loc:
                    lbl = sf.render(SHORT[loc], True, (255, 255, 255))
                    self.screen.blit(lbl, lbl.get_rect(center=rect.center))

                if view == "Crime Risk":
                    dep = getattr(self, "_ch5_deployment", {})
                    if nid in dep and dep[nid] > 0:
                        badge = tiny.render(f"P{dep[nid]}", True, (255, 255, 100))
                        self.screen.blit(badge, (rect.x + 2, rect.y + 2))

        if view == "Emergency" or self._em_mission is not None or self._em_picker is not None:
            self._draw_emergency_overlay(ox, oy, sz, sf, tiny)

        self._draw_blocked_roads(ox, oy, sz, view, tiny)
        self.screen.set_clip(None)

        # Horizontal legend bar at bottom of canvas
        self._draw_horizontal_legend(view, canvas, tiny, sf)

        # Pan hint chip
        hint_txt = "Scroll=zoom  •  Right-drag=pan  •  Ctrl+click=reset"
        hint = sf.render(hint_txt, True, C["text_dim"])
        chip = pygame.Rect(gx + 22, gy + 20, hint.get_width() + 20, hint.get_height() + 10)
        pygame.draw.rect(self.screen, (16, 24, 50, 200), chip, border_radius=12)
        pygame.draw.rect(self.screen, (54, 70, 112), chip, 1, border_radius=12)
        self.screen.blit(hint, (chip.x + 10, chip.y + 5))

    def _draw_horizontal_legend(self, view, canvas, tiny, sf):
        """Horizontal legend bar anchored at bottom of the map canvas."""
        BAR_H = 34
        bar = pygame.Rect(canvas.x + 10, canvas.bottom - BAR_H - 8,
                          canvas.w - 20, BAR_H)
        bar_surf = pygame.Surface((bar.w, bar.h), pygame.SRCALPHA)
        bar_surf.fill((10, 16, 38, 195))
        self.screen.blit(bar_surf, bar.topleft)
        pygame.draw.rect(self.screen, (55, 72, 120), bar, 1, border_radius=8)

        items = []
        if view == "City Layout":
            for t in LOCATION_TYPES:
                items.append((C[t], SHORT[t]))
        elif view == "Road Network":
            items = [(C["road_mst"], "MST"), (C["road_backup"], "Backup"),
                     (C["road_other"], "Other"), (C["road_blocked"], "Blocked")]
        elif view == "Ambulance":
            items = [(C["accent2"], "GA Depot"), (C["accent"], "Coverage")]
            worst = getattr(self, "_ga_worst", None)
            if worst is not None:
                items.append(((200, 200, 200), f"Worst: {worst:.1f}"))
        elif view == "Emergency":
            items = [(C["danger"], "Route"), (C["warn"], "Civilian"),
                     (C["accent2"], "Reached"), ((255, 255, 255), "Team")]
            m = self._em_mission
            if m:
                items.append(((200, 200, 200), f"{len(m.reached)}/{len(m.civilians)} done"))
        elif view == "Crime Risk":
            items = [((40, 180, 40), "Low"), ((220, 180, 38), "Medium"), ((210, 58, 58), "High")]
            preds = getattr(self, "_ch5_predictions", {})
            if preds:
                counts = {"High": 0, "Medium": 0, "Low": 0}
                for lv in preds.values():
                    counts[lv] = counts.get(lv, 0) + 1
                items.append(((180, 180, 180),
                               f"H:{counts['High']} M:{counts['Medium']} L:{counts['Low']}"))

        item_w = bar.w // max(1, len(items))
        for i, (col, label) in enumerate(items):
            ix = bar.x + i * item_w + 8
            iy = bar.centery
            pygame.draw.rect(self.screen, col, pygame.Rect(ix, iy - 5, 12, 12), border_radius=3)
            lbl = tiny.render(label, True, C["text_dim"])
            self.screen.blit(lbl, (ix + 16, iy - lbl.get_height() // 2))

    def _draw_roads(self, ox, oy, sz, view, tiny):
        """Draw non-blocked roads BEHIND cells with neon glow for MST/backup."""
        city = self.city; half = sz // 2; active_set = set(city.active_nodes)

        mst_set = set(); backup_set = set()
        if self.road_builder:
            mst_set    = {frozenset({u, v}) for u, v, _ in self.road_builder.mst_edges}
            backup_set = {frozenset({u, v}) for u, v, _ in self.road_builder.backup_edges}

        # Collect glow roads and regular roads separately
        glow_roads = []; plain_roads = []
        drawn = set()
        for node in city.active_nodes:
            r1, c1 = city.coords(node)
            for nb in city.neighbors(node):
                if nb not in active_set: continue
                key = frozenset({node, nb})
                if key in drawn: continue
                drawn.add(key)
                r2, c2 = city.coords(nb)
                x1 = ox + c1 * sz + half; y1 = oy + r1 * sz + half
                x2 = ox + c2 * sz + half; y2 = oy + r2 * sz + half

                edge_data = city.roads.get(node, {}).get(nb, {})
                if isinstance(edge_data, dict):
                    blocked = edge_data.get("blocked", False)
                    cost_val = edge_data.get("cost", 1.0)
                else:
                    blocked = False
                    lu = city.assignment.get(node); lv = city.assignment.get(nb)
                    cost_val = 0.8 if (lu == "Residential" or lv == "Residential") else 1.0

                if blocked: continue

                if key in mst_set:
                    glow_roads.append(((x1, y1), (x2, y2), C["road_mst"],
                                       max(3, sz // 12), cost_val, True))
                elif key in backup_set:
                    glow_roads.append(((x1, y1), (x2, y2), C["road_backup"],
                                       max(3, sz // 12), cost_val, True))
                else:
                    plain_roads.append(((x1, y1), (x2, y2)))

        # Draw plain roads first (no glow)
        for (x1, y1), (x2, y2) in plain_roads:
            pygame.draw.line(self.screen, C["road_other"], (x1, y1), (x2, y2), 2)

        # Draw glow roads on top
        for (x1, y1), (x2, y2), col, w, cost_val, show_cost in glow_roads:
            draw_glow_line(self.screen, (x1, y1), (x2, y2), col, w, glow_alpha=50)
            if show_cost and sz >= 52:
                mx = (x1 + x2) // 2; my = (y1 + y2) // 2
                ct = tiny.render(f"{cost_val:.1f}", True, (255, 255, 200))
                cr = ct.get_rect(center=(mx, my))
                pygame.draw.rect(self.screen, (8, 10, 20), cr.inflate(8, 4), border_radius=3)
                self.screen.blit(ct, cr)

    def _draw_emergency_overlay(self, ox, oy, sz, sf, tiny):
        """Next-level Ch4 overlay: glow routes, pulse halos, arrow heads, mission HUD."""
        import math
        city = self.city
        half = sz // 2
        mission = self._em_mission
        picker  = self._em_picker
        t_ms    = pygame.time.get_ticks()
        pulse   = 0.5 + 0.5 * math.sin(t_ms / 500)
        pulse2  = 0.5 + 0.5 * math.sin(t_ms / 300 + 1.2)

        route_ahead    = []
        route_behind   = []
        civilians_show = []
        start_node     = None
        team_pos       = None

        if picker:
            start_node     = picker.start
            civilians_show = [(n, False, i) for i, n in enumerate(picker.civilians)]
        elif mission:
            start_node = mission.start
            team_pos   = mission.current_pos
            if mission.route:
                route_behind = mission.route[:mission.step_idx + 1]
                route_ahead  = mission.route[mission.step_idx:]
            reached_set = set(mission.reached)
            for i, civ in enumerate(mission.civilians):
                civilians_show.append((civ, civ in reached_set, i))

        # ── Route lines with glow ────────────────────────────────────
        def node_pt(n):
            rr, cc = city.coords(n)
            return ox + cc * sz + half, oy + rr * sz + half

        if route_behind:
            for i in range(len(route_behind) - 1):
                p1 = node_pt(route_behind[i]); p2 = node_pt(route_behind[i + 1])
                pygame.draw.line(self.screen, (80, 30, 30), p1, p2, max(2, sz // 16))

        if route_ahead:
            for i in range(len(route_ahead) - 1):
                p1 = node_pt(route_ahead[i]); p2 = node_pt(route_ahead[i + 1])
                w = max(4, sz // 10)
                draw_glow_line(self.screen, p1, p2, C["danger"], w, glow_alpha=60)
                # Arrow head at segment midpoint (direction indicator)
                mx = (p1[0] + p2[0]) // 2; my = (p1[1] + p2[1]) // 2
                dx = p2[0] - p1[0]; dy = p2[1] - p1[1]
                length = math.hypot(dx, dy)
                if length > 0:
                    dx /= length; dy /= length
                    arr_sz = max(5, sz // 10)
                    tip = (mx + int(dx * arr_sz), my + int(dy * arr_sz))
                    left = (mx - int(dy * arr_sz * 0.5) - int(dx * arr_sz * 0.5),
                            my + int(dx * arr_sz * 0.5) - int(dy * arr_sz * 0.5))
                    right = (mx + int(dy * arr_sz * 0.5) - int(dx * arr_sz * 0.5),
                             my - int(dx * arr_sz * 0.5) - int(dy * arr_sz * 0.5))
                    pygame.draw.polygon(self.screen, (255, 80, 80), [tip, left, right])

        # ── Start / base node with animated ring ─────────────────────
        if start_node is not None:
            cx, cy = node_pt(start_node)
            base_r = max(9, sz // 5)
            ring_a = int(140 + 80 * pulse)
            for rr_off, alpha in [(base_r + 8, int(30 * pulse)), (base_r + 3, 60)]:
                ring_s = pygame.Surface((rr_off * 2 + 2, rr_off * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(ring_s, (0, 220, 100, alpha), (rr_off + 1, rr_off + 1), rr_off, 2)
                self.screen.blit(ring_s, (cx - rr_off - 1, cy - rr_off - 1))
            pygame.draw.circle(self.screen, (0, 220, 100), (cx, cy), base_r, 3)
            lbl = tiny.render("BASE", True, (0, 220, 100))
            self.screen.blit(lbl, lbl.get_rect(center=(cx, cy - base_r - 6)))

        # ── Civilian markers with pulsing halos ──────────────────────
        for civ_id, is_reached, idx in civilians_show:
            cx, cy = node_pt(civ_id)
            radius = max(8, sz // 6)
            if not is_reached:
                # Pulsing halo rings
                for ring_i in range(3):
                    ring_r = radius + 6 + ring_i * 7
                    ring_phase = pulse if ring_i % 2 == 0 else pulse2
                    ring_a = int(60 * ring_phase * (1 - ring_i * 0.3))
                    ring_s = pygame.Surface((ring_r * 2 + 2, ring_r * 2 + 2), pygame.SRCALPHA)
                    pygame.draw.circle(ring_s, (*C["warn"], ring_a),
                                       (ring_r + 1, ring_r + 1), ring_r, 2)
                    self.screen.blit(ring_s, (cx - ring_r - 1, cy - ring_r - 1))
                fill = C["warn"]
                border = (255, 220, 50)
                num_col = (20, 20, 20)
            else:
                fill = (55, 55, 55)
                border = (120, 200, 120)
                num_col = (160, 220, 160)

            pygame.draw.circle(self.screen, fill,   (cx, cy), radius)
            pygame.draw.circle(self.screen, border, (cx, cy), radius, 2)
            num = tiny.render(str(idx + 1), True, num_col)
            self.screen.blit(num, num.get_rect(center=(cx, cy)))

            if is_reached:
                pygame.draw.line(self.screen, (0, 200, 80), (cx - 4, cy), (cx - 1, cy + 4), 2)
                pygame.draw.line(self.screen, (0, 200, 80), (cx - 1, cy + 4), (cx + 5, cy - 4), 2)

        # ── Team position with animated glow ─────────────────────────
        if team_pos is not None and mission and mission.status == "active":
            cx, cy = node_pt(team_pos)
            d = max(9, sz // 5)
            # Glow pulse around team
            glow_r = int(d * 1.8 + d * 0.4 * pulse)
            glow_s = pygame.Surface((glow_r * 2 + 2, glow_r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_s, (*C["accent"], int(50 * pulse)),
                               (glow_r + 1, glow_r + 1), glow_r)
            self.screen.blit(glow_s, (cx - glow_r - 1, cy - glow_r - 1))
            pts = [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)]
            pygame.draw.polygon(self.screen, (220, 235, 255), pts)
            pygame.draw.polygon(self.screen, C["danger"], pts, 2)
            lbl = tiny.render("TEAM", True, (220, 235, 255))
            self.screen.blit(lbl, lbl.get_rect(center=(cx, cy + d + 5)))

        elif mission and mission.status in ("complete", "partial_complete"):
            if mission.reached:
                last = mission.reached[-1]
                cx, cy = node_pt(last)
                label = "PARTIAL" if mission.status == "partial_complete" else "DONE"
                done_s = sf.render(label, True, C["accent2"])
                pygame.draw.rect(self.screen, (10, 30, 20),
                                 done_s.get_rect(center=(cx, cy)).inflate(14, 8),
                                 border_radius=6)
                self.screen.blit(done_s, done_s.get_rect(center=(cx, cy)))

        # ── Mission HUD (top-right corner of map canvas) ─────────────
        if mission and mission.status == "active":
            W, H = self.screen.get_size()
            _, _, sw, th, lh, gx, gy, gw, gh = get_dims(self.screen)
            hud_w = 180; hud_h = 88
            hud_x = gx + gw - hud_w - 24; hud_y = gy + 18
            hud_s = pygame.Surface((hud_w, hud_h), pygame.SRCALPHA)
            hud_s.fill((8, 14, 32, 210))
            pygame.draw.rect(hud_s, (*C["danger"], 180),
                             pygame.Rect(0, 0, hud_w, hud_h), 1, border_radius=10)
            self.screen.blit(hud_s, (hud_x, hud_y))
            _, hud_sf, _, hud_tiny = make_fonts(H)
            self.screen.blit(hud_tiny.render("MISSION HUD", True, C["danger"]),
                             (hud_x + 10, hud_y + 8))
            pygame.draw.line(self.screen, (80, 30, 30),
                             (hud_x + 8, hud_y + 22), (hud_x + hud_w - 8, hud_y + 22), 1)
            rows = [
                (f"Civilians: {len(mission.reached)}/{len(mission.civilians)}", C["warn"]),
                (f"Re-routes: {mission.reroutes}", C["accent3"]),
                (f"Cost: {mission.total_cost:.1f}", C["text"]),
            ]
            ry = hud_y + 28
            for txt, col in rows:
                self.screen.blit(hud_tiny.render(txt, True, col), (hud_x + 10, ry))
                ry += 18

    def _draw_blocked_roads(self,ox,oy,sz,view,tiny):
        """Draw BLOCKED roads on top of cells. All markers stay inside the road gap."""
        city=self.city; half=sz//2; active_set=set(city.active_nodes)
        if not city.roads: return
        gap=CELL_MARGIN
        label_font=pygame.font.SysFont("Segoe UI",max(7,min(10,gap-2)))
        drawn=set()
        for node in city.active_nodes:
            for nb in city.neighbors(node):
                if nb not in active_set: continue
                key=frozenset({node,nb})
                if key in drawn: continue
                drawn.add(key)
                edge_data=city.roads.get(node,{}).get(nb,{})
                if not isinstance(edge_data,dict): continue
                if not edge_data.get("blocked",False): continue
                r1,c1=city.coords(node); r2,c2=city.coords(nb)
                # Cell centres
                cx1=ox+c1*sz+half; cy1=oy+r1*sz+half
                cx2=ox+c2*sz+half; cy2=oy+r2*sz+half
                mx=(cx1+cx2)//2; my=(cy1+cy2)//2
                # Road line runs only through the GAP between cells, not through cells.
                # Cell body spans [cell_origin+m .. cell_origin+sz-m].
                # Gap midpoint is the cell boundary: ox+c*sz+sz for horizontal,
                # oy+r*sz+sz for vertical.
                # We draw from (cell_edge + m) to (next_cell_edge - m) on each axis.
                m=CELL_MARGIN
                if r1==r2:
                    # Horizontal road — same row, different col
                    left_col=min(c1,c2); right_col=max(c1,c2)
                    lx=ox+left_col*sz+sz-m+1   # just past left cell right edge
                    rx=ox+right_col*sz+m-1      # just before right cell left edge
                    lx=max(lx,mx-gap//2); rx=min(rx,mx+gap//2)
                    sx1=lx; sy1=my; sx2=rx; sy2=my
                else:
                    # Vertical road — same col, different row
                    top_row=min(r1,r2); bot_row=max(r1,r2)
                    ty=oy+top_row*sz+sz-m+1
                    by=oy+bot_row*sz+m-1
                    ty=max(ty,my-gap//2); by=min(by,my+gap//2)
                    sx1=mx; sy1=ty; sx2=mx; sy2=by
                w=max(3,min(gap-2,sz//14))
                pygame.draw.line(self.screen,(210,35,35),(sx1,sy1),(sx2,sy2),w)
                # X cross arms — fits inside the gap
                hw=max(3,min(gap//2-2,6))
                pygame.draw.line(self.screen,(255,255,255),(mx-hw,my-hw),(mx+hw,my+hw),2)
                pygame.draw.line(self.screen,(255,255,255),(mx+hw,my-hw),(mx-hw,my+hw),2)
                # Tiny "X" label at exact midpoint
                xt=label_font.render("X",True,(255,200,200))
                self.screen.blit(xt,xt.get_rect(center=(mx,my)))

    def _draw_legend(self,view,gx,gy,gw,gh,sf):
        """Legend is now drawn in the sidebar by _draw_sidebar_legend — nothing here."""
        pass

    # ── Bottom Area: Event Log (60%) + Sim/Stats Panel (40%) ──────────
    def _draw_bottom_area(self):
        W, H = self.screen.get_size()
        _, _, sw, th, lh, gx, _, gw, _ = get_dims(self.screen)
        font, sf, bf, tiny = make_fonts(H)
        log_y = H - lh + 8
        full_rect = pygame.Rect(gx + 10, log_y, gw - 20, lh - 16)

        split = int(full_rect.w * 0.62)
        log_rect  = pygame.Rect(full_rect.x, full_rect.y, split - 5, full_rect.h)
        stat_rect = pygame.Rect(full_rect.x + split + 5, full_rect.y,
                                full_rect.w - split - 5, full_rect.h)

        # ── Event log panel ──────────────────────────────────────────
        draw_card(self.screen, log_rect, fill=C["panel"], border=(48, 63, 103), radius=14, shadow=True)
        hdr = sf.render("EVENT LOG", True, C["accent"])
        self.screen.blit(hdr, (log_rect.x + 14, log_rect.y + 10))
        help_t = tiny.render("scroll", True, C["muted"])
        self.screen.blit(help_t, (log_rect.right - help_t.get_width() - 12, log_rect.y + 13))
        pygame.draw.line(self.screen, (44, 59, 98),
                         (log_rect.x + 12, log_rect.y + 34),
                         (log_rect.right - 12, log_rect.y + 34), 1)

        line_h = max(16, sf.get_height() + 2)
        usable_w = log_rect.w - 32
        visible_area_h = log_rect.h - 48
        visible_lines = max(1, visible_area_h // line_h)

        display_lines = []
        for idx, entry in enumerate(self.log):
            words = entry.split(" ")
            cur = ""
            for word in words:
                test = cur + (" " if cur else "") + word
                if sf.size(test)[0] > usable_w and cur:
                    display_lines.append((cur, idx == len(self.log) - 1))
                    cur = word
                else:
                    cur = test
            if cur:
                display_lines.append((cur, idx == len(self.log) - 1))

        total = len(display_lines)
        self.log_scroll = min(self.log_scroll, max(0, total - visible_lines))
        end = total - self.log_scroll
        start = max(0, end - visible_lines)
        visible = display_lines[start:end]
        body = pygame.Rect(log_rect.x + 12, log_rect.y + 40, log_rect.w - 24, log_rect.h - 50)
        self.screen.set_clip(body)
        for i, (txt, is_latest) in enumerate(visible):
            col = C["text"] if is_latest else C["text_dim"]
            if is_latest:
                pygame.draw.circle(self.screen, C["accent2"],
                                   (body.x + 5, body.y + i * line_h + line_h // 2), 3)
                x = body.x + 14
            else:
                x = body.x
            self.screen.blit(sf.render(txt, True, col), (x, body.y + i * line_h))
        self.screen.set_clip(None)
        if total > visible_lines:
            track = pygame.Rect(log_rect.right - 8, body.y, 4, body.h)
            pygame.draw.rect(self.screen, (36, 48, 80), track, border_radius=4)
            sb_h = max(20, int(body.h * visible_lines / total))
            frac = 1.0 - (self.log_scroll / max(1, total - visible_lines))
            sb_y = track.y + int((track.h - sb_h) * frac)
            pygame.draw.rect(self.screen, C["accent"],
                             pygame.Rect(track.x, sb_y, track.w, sb_h), border_radius=4)

        # ── Right stats/sim panel ────────────────────────────────────
        draw_card(self.screen, stat_rect, fill=(14, 20, 44), border=(58, 80, 145), radius=14, shadow=True)
        self.screen.blit(sf.render("SIM & STATS", True, C["accent3"]),
                         (stat_rect.x + 14, stat_rect.y + 10))
        pygame.draw.line(self.screen, (44, 60, 105),
                         (stat_rect.x + 12, stat_rect.y + 34),
                         (stat_rect.right - 12, stat_rect.y + 34), 1)

        sy = stat_rect.y + 42
        # Sim progress bar
        step = getattr(self._sim_state, "steps_completed", 0) if self._sim_state else 0
        sim_status = ("Auto" if self._sim_auto_running else
                      "Running" if self._sim_running else
                      "Ready" if self._sim_controller else "—")
        self.screen.blit(tiny.render(f"SIMULATION  {step}/20  [{sim_status}]",
                                     True, C["muted"]), (stat_rect.x + 14, sy))
        sy += 16
        bar_r = pygame.Rect(stat_rect.x + 14, sy, stat_rect.w - 28, 8)
        pygame.draw.rect(self.screen, (34, 47, 82), bar_r, border_radius=5)
        if step:
            fill_w = max(5, int(bar_r.w * step / 20))
            pygame.draw.rect(self.screen, C["accent2"],
                             pygame.Rect(bar_r.x, bar_r.y, fill_w, bar_r.h), border_radius=5)
        sy += 16

        # Mission quick stats
        m = self._em_mission
        quick = [
            ("Nodes",    str(len(self.city.active_nodes)),          C["accent"]),
            ("Roads",    str(sum(len(v) for v in self.city.roads.values()) // 2
                            if self.city.roads else 0),              C["road_mst"]),
            ("Ambul.",   str(len(self.ambulance_nodes)),             C["accent2"]),
            ("Reached",  f"{len(m.reached)}/{len(m.civilians)}" if m else "—",
             C["warn"] if m else C["muted"]),
            ("Reroutes", str(m.reroutes) if m else "—",
             C["accent3"] if m and m.reroutes else C["muted"]),
        ]
        cols_count = 2
        col_w = (stat_rect.w - 28) // cols_count
        for i, (label, val, col) in enumerate(quick):
            qx = stat_rect.x + 14 + (i % cols_count) * col_w
            qy = sy + (i // cols_count) * 22
            pygame.draw.circle(self.screen, col, (qx + 5, qy + 8), 4)
            self.screen.blit(tiny.render(label, True, C["muted"]), (qx + 14, qy))
            self.screen.blit(tiny.render(str(val), True, C["text"]), (qx + 14, qy + 10))

    def _draw_popup(self):
        W,H=self.screen.get_size()
        font,_,_,_=make_fonts(H)
        p=self.popup; ov=pygame.Surface((W,H),pygame.SRCALPHA)
        ov.fill((0,0,0,160)); self.screen.blit(ov,(0,0))
        pygame.draw.rect(self.screen,C["panel"],p["rect"],border_radius=10)
        pygame.draw.rect(self.screen,C["accent"],p["rect"],1,border_radius=10)
        rx,ry,_,_=p["rect"]
        self.screen.blit(font.render(p["title"],True,C["text"]),(rx+16,ry+14))
        for _,b in p["btns"]: b.draw(self.screen,font)

    def _log(self,msg):
        safe=str(msg).encode("ascii","replace").decode("ascii")
        self.log.append(safe)
        self.log_scroll=0   # auto-scroll to bottom on new entry
        if len(self.log)>500: self.log.pop(0)


# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    pygame.init()
    # Detect best compatible resolution (leave 60px margin for taskbar/chrome)
    info = pygame.display.Info()
    W = max(1280, min(info.current_w - 60, 1680))
    H = max(820,  min(info.current_h - 60, 1020))
    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    pygame.display.set_caption("CityMind -- Urban Intelligence System")
    clock=pygame.time.Clock()

    # Phase 1
    setup=SetupScreen(screen)
    while not setup.done:
        for ev in pygame.event.get():
            if ev.type==pygame.QUIT: pygame.quit(); sys.exit()
            if ev.type==pygame.VIDEORESIZE:
                screen=pygame.display.set_mode(ev.size,pygame.RESIZABLE)
                setup.screen=screen; setup._rebuild()
            setup.handle(ev)
        setup.draw(); pygame.display.flip(); clock.tick(60)

    rows,cols,num_nodes,tc,bt,mc=setup.result

    # Phase 2
    loader=LoadingScreen(screen,rows,cols,num_nodes,tc,bt,mc)
    while not loader.done:
        for ev in pygame.event.get():
            if ev.type==pygame.QUIT: pygame.quit(); sys.exit()
            if ev.type==pygame.VIDEORESIZE:
                screen=pygame.display.set_mode(ev.size,pygame.RESIZABLE)
                loader.screen=screen
        loader.update(); loader.draw(); pygame.display.flip(); clock.tick(60)

    # Phase 3
    gui=CityMindGUI(screen,loader.manager,bt,mc,loader.csp_log)
    while True:
        for ev in pygame.event.get():
            if ev.type==pygame.QUIT: pygame.quit(); sys.exit()
            if ev.type==pygame.VIDEORESIZE:
                screen=pygame.display.set_mode(ev.size,pygame.RESIZABLE)
                gui.screen=screen
                gui.violation_panel and setattr(gui.violation_panel,"screen",screen)
                gui.hospital_picker and setattr(gui.hospital_picker,"screen",screen)
                gui._build_ui()
            gui.handle(ev)
        gui.draw(); clock.tick(60)

if __name__=="__main__":
    main()