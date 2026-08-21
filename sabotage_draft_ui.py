import json
from nicegui import ui, app
from sabotage_draft import DraftSession, get_all_players, get_all_icons, active_draft
import sabotage_draft

def format_card(p):
    playstyles = ""
    if not p.get("is_icon") and "play_styles" in p:
        ps_list = p.get("play_styles", [])
        if ps_list:
            playstyles = " | ".join(ps_list)
    elif p.get("is_icon"):
        playstyles = "⭐ LEGEND"
        
    alt = p.get('alt_positions', '')
    pos_str = f"{p.get('position', '')} ({alt})" if alt and str(alt).lower() != 'nan' else p.get('position', '')
    
    foot = p.get('preferred_foot', 'Unknown')
    if not foot or foot == "?": foot = 'Unknown'
    
    sm = p.get('skill_moves', '')
    sm_str = f" | {int(sm)}★ Skills" if sm else ""
    
    pac = p.get('pace') or 0
    sho = p.get('shooting') or 0
    pas = p.get('passing') or 0
    dri = p.get('dribbling') or 0
    defn = p.get('defending') or 0
    phy = p.get('physical') or 0
    
    stats_html = f"""
    <div style="display: grid; grid-template-columns: 1fr 1fr; font-size: 11px; margin-top: 6px; color: #444; line-height: 1.2;">
        <div><b>{pac}</b> PAC</div><div><b>{dri}</b> DRI</div>
        <div><b>{sho}</b> SHO</div><div><b>{defn}</b> DEF</div>
        <div><b>{pas}</b> PAS</div><div><b>{phy}</b> PHY</div>
    </div>
    """
        
    return f"""
    <div style="text-align: center;">
        <b>{p.get('name', 'Unknown')}</b><br>
        <span style="font-size: 18px; font-weight: bold;">{p.get('overall', 0)} {pos_str}</span><br>
        <span style="font-size: 12px; color: gray;">{foot} foot{sm_str}</span><br>
        <span style="font-size: 11px; color: darkorange;">{playstyles}</span>
        {stats_html}
    </div>
    """

def draft_setup_page():
    @ui.page('/draft/setup')
    def setup():
        ui.label("Sabotage Draft - Setup").classes("text-h4 mb-4")
        
        with ui.card().classes("w-full max-w-xl mx-auto p-4"):
            ui.label("Teams & Rules").classes("text-h6")
            
            team_a = ui.input("Team A Name (You)", value="Liverpool").classes("w-full")
            team_b = ui.input("Team B Name (Opponent)", value="Man Utd").classes("w-full")
            
            with ui.row().classes("w-full gap-4"):
                min_ovr = ui.number("Min OVR (0=No min)", value=80, format="%.0f").classes("flex-1")
                max_ovr = ui.number("Max OVR (0=No max)", value=92, format="%.0f").classes("flex-1")
                
            allow_legends = ui.checkbox("Include Legends / Icons", value=True).classes("mt-4")
            
            with ui.row().classes("w-full gap-4 mt-2"):
                cards_per_round = ui.number("Cards per Round", value=5, min=2, max=7, format="%.0f").classes("flex-1")
                blocks_per_round = ui.number("Blocks per Round (0 = No Bans / Pure Draft)", value=1, min=0, max=1, format="%.0f").classes("flex-1")
                
            opponent_first = ui.checkbox("Opponent Goes First (Round 1)", value=True).classes("mt-2")
            
            def start_draft():
                num_blocks = int(blocks_per_round.value or 0)
                sabotage_draft.active_draft = DraftSession(
                    team_a.value, team_b.value,
                    int(min_ovr.value or 0), int(max_ovr.value or 0),
                    allow_legends.value, int(cards_per_round.value or 5),
                    opponent_first.value,
                    allow_blocking=(num_blocks > 0)
                )
                ui.navigate.to('/draft/board')
                
            ui.button("Start Draft", on_click=start_draft).classes("w-full mt-6").props("color=primary size=lg")

def draft_board_page():
    @ui.page('/draft/board')
    def board():
        draft = sabotage_draft.active_draft
        if not draft:
            ui.navigate.to('/draft/setup')
            return
            
        if draft.state == "FINISHED":
            ui.navigate.to('/draft/summary')
            return

        active_team, action_type = draft.get_turn_info()
        
        with ui.row().classes("w-full justify-between items-center bg-gray-100 p-2 rounded"):
            ui.label(f"Round {draft.round_number} / {draft.max_rounds}").classes("text-h6")
            
            action_color = "red" if action_type == "BAN" else "green" if action_type == "PICK" else "orange"
            action_text = f"BAN a player" if action_type == "BAN" else f"PICK a player" if action_type == "PICK" else f"Take LEFTOVERS"
            
            ui.label(f"{active_team}'s Turn to {action_text}").classes(f"text-h5 text-{action_color}-600 font-bold")

        with ui.row().classes("w-full mt-4 flex-nowrap"):
            # LEFT SQUAD
            with ui.column().classes("w-1/4 p-2 bg-blue-50 border"):
                ui.label(draft.team_a_name).classes("text-lg font-bold")
                for p in draft.team_a_squad:
                    alt = p.get('alt_positions', '')
                    pos = f"{p.get('position', '')} ({alt})" if alt and str(alt).lower() != 'nan' else p.get('position', '')
                    foot = p.get('preferred_foot', '?')
                    foot = foot[:1] if foot else '?'
                    ui.label(f"{p.get('overall', 0)} {pos} - {p.get('name', '')} ({foot})").classes("text-sm")
                    
            # CENTER BOARD
            with ui.column().classes("w-1/2 px-4 items-center"):
                ui.label("Select a Card").classes("text-h6 mb-2")
                
                with ui.row().classes("w-full justify-center gap-4"):
                    card_elements = []
                    
                    for idx, p in enumerate(draft.current_board):
                        is_banned = (idx == draft.banned_idx)
                        is_picked = (idx == draft.picked_idx) or (idx == draft.first_picked_idx) or (idx == draft.second_picked_idx)
                        
                        card = ui.card().classes("w-32 items-center cursor-pointer")
                        if is_banned:
                            card.classes("bg-red-200 opacity-50")
                        elif is_picked:
                            card.classes("bg-green-200 opacity-50")
                        else:
                            card.classes("hover:bg-gray-100 transition-colors")
                            
                        with card:
                            ui.html(format_card(p))
                            ui.label(f"[{idx+1}]").classes("text-xs font-bold text-gray-400 mt-2")
                            
                        # Store click handler via closure
                        def make_handler(i):
                            def handler():
                                if draft.take_action(i):
                                    # Refresh page
                                    ui.navigate.to('/draft/board')
                            return handler
                            
                        if not is_banned and not is_picked:
                            card.on("click", make_handler(idx))
                            
                # Keyboard shortcuts info
                ui.label(f"Press 1-{len(draft.current_board)} to select").classes("text-xs text-gray-500 mt-8")
                
                # Add keyboard listener
                def handle_key(e):
                    key = e.key
                    if key.isdigit():
                        idx = int(key) - 1
                        if 0 <= idx < len(draft.current_board):
                            if draft.take_action(idx):
                                ui.navigate.to('/draft/board')
                
                ui.keyboard(on_key=handle_key)

            # RIGHT SQUAD
            with ui.column().classes("w-1/4 p-2 bg-red-50 border"):
                ui.label(draft.team_b_name).classes("text-lg font-bold")
                for p in draft.team_b_squad:
                    alt = p.get('alt_positions', '')
                    pos = f"{p.get('position', '')} ({alt})" if alt and str(alt).lower() != 'nan' else p.get('position', '')
                    foot = p.get('preferred_foot', '?')
                    foot = foot[:1] if foot else '?'
                    ui.label(f"{p.get('overall', 0)} {pos} - {p.get('name', '')} ({foot})").classes("text-sm")


def draft_summary_page():
    @ui.page('/draft/summary')
    def summary():
        draft = sabotage_draft.active_draft
        if not draft or draft.state != "FINISHED":
            ui.navigate.to('/draft/setup')
            return
            
        ui.label("Draft Complete!").classes("text-h4 mb-4 text-center w-full")
        
        with ui.row().classes("w-full justify-center gap-4 mb-6"):
            if draft.team_a_gk:
                with ui.card().classes("bg-yellow-100 p-4 items-center text-center"):
                    ui.html(f"<b>Team A Goalkeeper</b><br>{draft.team_a_gk.get('overall', 0)} {draft.team_a_gk.get('position', '')} - {draft.team_a_gk.get('name', '')}")
            if draft.team_b_gk:
                with ui.card().classes("bg-yellow-100 p-4 items-center text-center"):
                    ui.html(f"<b>Team B Goalkeeper</b><br>{draft.team_b_gk.get('overall', 0)} {draft.team_b_gk.get('position', '')} - {draft.team_b_gk.get('name', '')}")

        with ui.row().classes("w-full flex-nowrap gap-4"):
            for team_name, squad, gk in [
                (draft.team_a_name, draft.team_a_squad, draft.team_a_gk),
                (draft.team_b_name, draft.team_b_squad, draft.team_b_gk)
            ]:
                with ui.column().classes("w-1/2 p-4 border rounded bg-gray-50"):
                    avg_ovr = sum(p.get("overall", 0) for p in squad) / max(1, len(squad))
                    ui.label(f"{team_name} (Avg: {avg_ovr:.1f})").classes("text-h5 font-bold mb-2")
                    
                    if gk:
                        ui.label(f"GK: {gk.get('overall', 0)} - {gk.get('name', '')}").classes("font-bold text-blue-600 mb-2")
                        
                    for p in squad:
                        playstyles = " | ".join(p.get("play_styles", [])) if "play_styles" in p else ("⭐ LEGEND" if p.get("is_icon") else "")
                        ui.html(f"<b>{p.get('overall', 0)} {p.get('position', '')}</b> - {p.get('name', '')} <span style='color:gray;font-size:12px;'>({playstyles})</span>")
                        
        with ui.row().classes("w-full justify-center mt-8 gap-4 items-center"):
            def export_squads():
                from shortlist import Shortlist, ShortlistPlayer, save_preset
                
                sl = Shortlist(target_team=0, target_name="Draft Match")
                
                def add_player(p_dict, t_id):
                    sl.add(ShortlistPlayer(
                        player_id=p_dict["player_id"],
                        name=p_dict["name"],
                        overall=p_dict.get("overall"),
                        position=p_dict.get("position"),
                        target_team=t_id
                    ))

                from sabotage_draft import resolve_team_id
                tid_a = resolve_team_id(draft.team_a_name, 8)
                tid_b = resolve_team_id(draft.team_b_name, 10)

                # Team A -> Liverpool (8) by default
                if draft.team_a_gk:
                    add_player(draft.team_a_gk, tid_a)
                for p in draft.team_a_squad:
                    add_player(p, tid_a)
                    
                # Team B -> Man Utd (10) by default
                if draft.team_b_gk:
                    add_player(draft.team_b_gk, tid_b)
                for p in draft.team_b_squad:
                    add_player(p, tid_b)
                    
                save_preset(sl, "draft")
                ui.notify("Successfully exported both teams to draft.json!", type='positive')

            ui.button("Export to draft.json", on_click=export_squads).props("color=primary size=lg icon=save")
            ui.button("Play Again", on_click=lambda: ui.navigate.to('/draft/setup')).props("flat")

def init_draft_routes():
    draft_setup_page()
    draft_board_page()
    draft_summary_page()
