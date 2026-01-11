# Released under the MIT License.
#
"""Custom Team Series Victory Screen (MVP vs Killer)."""

from __future__ import annotations

from typing import TYPE_CHECKING, override, cast, Any
import random
import weakref
from functools import partial

import _bascenev1
import bascenev1 as bs
import babase
from bascenev1._messages import PlayerDiedMessage, StandMessage
from bascenev1._music import MusicType
from bascenev1._activity import Activity
from bascenev1._player import Player
from bascenev1._team import SessionTeam, Team
#from bascenev1lib.activity.multiteamscore import MultiTeamScoreScreenActivity
from bascenev1lib.actor.text import Text
from bascenev1lib.actor.image import Image
from bascenev1lib.actor.zoomtext import ZoomText
from bascenev1lib.actor.playerspaz import PlayerSpaz
from bascenev1lib.gameutils import SharedObjects

if TYPE_CHECKING:
    pass




# ============================================================================
# CUSTOM VICTORY ACTIVITY
# ============================================================================

class Player(bs.Player['Team']):
    """Our player type for this game."""


class Team(bs.Team[Player]):
    """Our team type for this game."""
    
class MVPVsKillerScoreScreenActivity(Activity[Player, Team]):
    """Replaces multiteamvictory.TeamSeriesVictoryScoreScreenActivity."""
    
    
    transition_time = 0.5
    inherits_tint = True
    inherits_vr_camera_offset = True
    use_fixed_vr_overlay = True
    default_music: MusicType | None = None  # handled manually

    def __init__(self, settings: dict):
        super().__init__(settings=settings)
        shared = SharedObjects.get()
        footing_material = shared.footing_material
        object_material = shared.object_material
        player_material = shared.player_material
        region_material = shared.region_material
        self.spaz_material = bs.Material()
        self.roller_material = bs.Material()
        
        self._spawn_sound = _bascenev1.getsound('spawn')
        self._min_view_time = 15.0
        self._allow_server_transition = True
        self._tips_text = None
        self._default_show_tips = False
        self._custom_continue_message: babase.Lstr | None = None
        self._server_transitioning: bool | None = None
        self._background: bs.Actor | None = None
        
        # Add properties from ScoreScreenActivity
        self._birth_time = babase.apptime()
        self._kicked_off_server_shutdown = False
        self._kicked_off_server_restart = False
        
        # MVP and Killer data
        self._mvp_record: bs.PlayerRecord | None = None
        self._killer_record: bs.PlayerRecord | None = None
        self._mvp_name = ""
        self._killer_name = ""
        self._mvp_score = 0
        self._killer_kills = 0
        
        # Actors
        self._countdown_text = None
        self._status_text = None
        self._timer_text = None
        self._mvp_health_bar = None
        self._killer_health_bar = None
        self._mvp_spaz = None
        self._killer_spaz = None

        

        self.spaz_material.add_actions(
            conditions=('they_have_material', footing_material),
            actions=(
                ('message', 'our_node', 'at_connect', 'footing', 1),
                ('message', 'our_node', 'at_disconnect', 'footing', -1),
            ),
        )
        print("✅ MVPVsKillerScoreScreenActivity CREATED")

    @override
    def on_transition_in(self) -> None:
        from bascenev1lib.actor.background import Background

        super().on_transition_in()
        
        # # Create background
        # self._background = Background(
            # fade_time=0.5, start_faded=False, show_logo=True
        # )
        
        
        
        bs.setmusic(self.default_music)

   

    @override
    def on_player_join(self, player: Player) -> None:
        # First call parent to handle basic setup
        super().on_player_join(player)
        
        # Set up input assignment after min view time
        time_till_assign = max(
            0, self._birth_time + self._min_view_time - babase.apptime()
        )

        # Assign input to player after delay
        if time_till_assign > 0:
            bs.timer(
                time_till_assign, 
                babase.WeakCall(self._safe_assign, player)
            )

    @override
    def on_begin(self) -> None:
        super().on_begin()
        
        self._birth_time = babase.apptime()
        self._create_map()
        bs.set_analytics_screen('MVP vs Killer Victory Screen')
        print(self.players)
        assert bs.app.classic is not None
        if bs.app.ui_v1.uiscale is bs.UIScale.LARGE:
            sval = bs.Lstr(resource='pressAnyKeyButtonPlayAgainText')
        else:
            sval = bs.Lstr(resource='pressAnyButtonPlayAgainText')
        
        self._custom_continue_message = sval
        
        # Show continue message
        Text(
            self._custom_continue_message,
            v_attach=Text.VAttach.BOTTOM,
            h_align=Text.HAlign.CENTER,
            flash=True,
            vr_depth=50,
            position=(0, 10),
            scale=0.8,
            color=(0.5, 0.7, 0.5, 0.5),
            transition=Text.Transition.IN_BOTTOM_SLOW,
            transition_delay=self._min_view_time,
        ).autoretain()
        
        # Pause a moment before playing victory music.
        bs.timer(0.6, bs.WeakCall(self._play_victory_music))
        
        # Get player records
        self._process_player_records()
        
        # Clear any existing actors
        self._clear_existing_actors()
        
        # Spawn MVP and Killer
        self._spawn_mvp_and_killer()

    
    def _create_map(self) -> None:
        """Create a football stadium map for the victory screen."""
        shared = SharedObjects.get()
        
        # Create the main terrain node (the actual playable surface)
        self.node = bs.newnode(
            'terrain',
            delegate=self,
            attrs={
                'mesh': bs.getmesh('footballStadium'),
                'collision_mesh': bs.getcollisionmesh('footballStadiumCollide'),
                'color_texture': bs.gettexture('footballStadium'),
                'materials': [shared.footing_material],
                'position': (0, 0, 0),  # Explicit position
            },
        )
        
        # The VR fill mesh (only visible in VR)
        bs.newnode(
            'terrain',
            attrs={
                'mesh': bs.getmesh('footballStadiumVRFill'),
                'lighting': False,
                'vr_only': True,
                'background': True,
                'color_texture': bs.gettexture('footballStadium'),
            },
        )
        
        # Set global node properties like the original FootballStadium
        gnode = bs.getactivity().globalsnode
        gnode.tint = (1.3, 1.2, 1.0)
        gnode.ambient_color = (1.3, 1.2, 1.0)
        gnode.vignette_outer = (0.57, 0.57, 0.57)
        gnode.vignette_inner = (0.9, 0.9, 0.9)
        gnode.vr_camera_offset = (0, -0.8, -1.1)
        gnode.vr_near_clip = 0.5
        
        print("DEBUG: Football stadium map created successfully")
        print(f"DEBUG: Main node: {self.node}")
        
        
    def _process_player_records(self) -> None:
        """Process player records to find MVP and Killer."""
        player_entries: list[tuple[int, str, bs.PlayerRecord]] = []

        # Get all player records
        for _pkey, prec in self.stats.get_records().items():
            player_entries.append((prec.score, prec.name_full, prec))
        player_entries.sort(reverse=True, key=lambda x: x[0])

        # Find MVP (highest score)
        if player_entries:
            self._mvp_record = player_entries[0][2]
            self._mvp_name = player_entries[0][1]
            self._mvp_score = player_entries[0][0]

        # Find Killer (most kills)
        most_kills = 0
        for entry in player_entries:
            if entry[2].kill_count >= most_kills:
                self._killer_record = entry[2]
                self._killer_name = entry[1]
                self._killer_kills = entry[2].kill_count
                most_kills = entry[2].kill_count

    def _clear_existing_actors(self) -> None:
        """Clear any existing player actors."""
        for player in self.players:
            if player.actor:
                player.actor.handlemessage(bs.DieMessage())

    def _spawn_mvp_and_killer(self) -> None:
        """Spawn MVP and Killer player spazes."""

        # Spawn positions
        mvp_pos = (-2.0, 1.0, 0.0)
        killer_pos = (2.0, 1.0, 0.0)

        mvp_player = None
        killer_player = None

        # Find matching players by name
        for player in self.players:
            if not player.exists():
                continue

            name = player.getname(full=True)

            if name == self._mvp_name:
                mvp_player = player

            if name == self._killer_name:
                killer_player = player

        if mvp_player:
            print(f"Spawning MVP: {self._mvp_name}")
            try:
                # Call spawn_player_spaz directly
                self._mvp_spaz = self.spawn_player_spaz(
                    mvp_player, 
                    position=mvp_pos,
                    angle=0  # Fixed angle
                )
            except Exception as e:
                print(f"Error spawning MVP: {e}")
        
        # Spawn Killer
        if killer_player and killer_player is not mvp_player:
            print(f"Spawning Killer: {self._killer_name}")
            try:
                # Call spawn_player_spaz directly
                self._killer_spaz = self.spawn_player_spaz(
                    killer_player, 
                    position=killer_pos,
                    angle=180  # Facing MVP
                )
            except Exception as e:
                print(f"Error spawning Killer: {e}")

        # Display MVP vs Killer text
        self._show_mvp_vs_killer_text()

    def _play_victory_music(self) -> None:
        """Play victory music."""
        if not self.is_transitioning_out():
            bs.setmusic(bs.MusicType.VICTORY)

    def _show_mvp_vs_killer_text(self) -> None:
        """Display MVP vs Killer text."""
        # Title
        Text(
            "MVP vs KILLER",
            position=(0, 3.5),
            h_align=Text.HAlign.CENTER,
            scale=1.5,
            color=(1, 1, 1, 1),
            transition=Text.Transition.FADE_IN,
            transition_delay=1.0
        ).autoretain()
        
        # MVP Info
        if self._mvp_record:
            Text(
                f"MVP: {self._mvp_name}",
                position=(-4, 2.0),
                h_align=Text.HAlign.LEFT,
                scale=1.2,
                color=(0.2, 0.8, 0.2, 1),
                transition=Text.Transition.FADE_IN,
                transition_delay=1.5
            ).autoretain()
            
            Text(
                f"Score: {self._mvp_score}",
                position=(-4, 0.5),
                h_align=Text.HAlign.RIGHT,
                scale=0.8,
                color=(0.3, 0.9, 0.3, 1),
                transition=Text.Transition.FADE_IN,
                transition_delay=2.0
            ).autoretain()
        
        # Killer Info
        if self._killer_record:
            Text(
                f"KILLER: {self._killer_name}",
                position=(4, -6.5),
                h_align=Text.HAlign.RIGHT,
                scale=1.2,
                color=(0.8, 0.2, 0.2, 1),
                transition=Text.Transition.FADE_IN,
                transition_delay=1.5
            ).autoretain()
            
            Text(
                f"Kills: {self._killer_kills}",
                position=(4, 4.5),
                h_align=Text.HAlign.RIGHT,
                scale=0.8,
                color=(0.9, 0.3, 0.3, 1),
                transition=Text.Transition.FADE_IN,
                transition_delay=2.0
            ).autoretain()

    def _player_press(self) -> None:
        """Handle player input to continue."""
        # If server-mode is handling this, don't do anything ourself.
        if self._server_transitioning is True:
            return

        # Otherwise end the activity normally.
        self.end()

    def _safe_assign(self, player: Player) -> None:
        """Safely assign input to player."""
        if not self.is_transitioning_out() and player and player.exists():
            try:
                player.assigninput(
                    (
                        babase.InputType.JUMP_PRESS,
                        babase.InputType.PUNCH_PRESS,
                        babase.InputType.BOMB_PRESS,
                        babase.InputType.PICK_UP_PRESS,
                    ),
                    self._player_press,
                )
            except Exception as e:
                print(f"Error assigning input to player: {e}")

    @override
    def on_transition_out(self) -> None:
        """Clean up when transitioning out."""
        # Clean up any remaining actors
        actors_to_clean = [
            self._countdown_text,
            self._status_text,
            self._timer_text,
            self._mvp_health_bar,
            self._killer_health_bar,
            self._mvp_spaz,
            self._killer_spaz
        ]
        
        for actor in actors_to_clean:
            if actor:
                try:
                    actor.handlemessage(bs.DieMessage())
                except:
                    pass
        
        # Clear references
        self._countdown_text = None
        self._status_text = None
        self._timer_text = None
        self._mvp_health_bar = None
        self._killer_health_bar = None
        self._mvp_spaz = None
        self._killer_spaz = None
        
        # Call parent cleanup
        super().on_transition_out()

    @override
    def spawn_player(self, player: Player, position) -> bs.Actor:
        """Spawn a player as a spaz."""
        # Simply delegate to the working spawn_player_spaz method
        return self.spawn_player_spaz(player, position=position)
        
        
    def spawn_player_spaz(
        self,
        player: PlayerT,
        position: Sequence[float] = (0, 0, 0),
        angle: float | None = None,
    ) -> PlayerSpaz:
        """Create and wire up a player-spaz for the provided player."""
        # pylint: disable=too-many-locals
        # pylint: disable=cyclic-import
        from bascenev1._gameutils import animate
        from bascenev1._coopsession import CoopSession
        from bascenev1lib.actor.playerspaz import PlayerSpaz

        name = player.getname()
        color = player.color
        highlight = player.highlight

        playerspaztype = getattr(player, 'playerspaztype', PlayerSpaz)
        if not issubclass(playerspaztype, PlayerSpaz):
            playerspaztype = PlayerSpaz

        light_color = babase.normalized_color(color)
        display_color = babase.safecolor(color, target_intensity=0.75)
        spaz = playerspaztype(
            color=color,
            highlight=highlight,
            character=player.character,
            player=player,
        )

        player.actor = spaz
        assert spaz.node

        # If this is co-op and we're on Courtyard or Runaround, add the
        # material that allows us to collide with the player-walls.
        # FIXME: Need to generalize this.
       

        spaz.node.name = name
        spaz.node.name_color = display_color
        spaz.connect_controls_to_player()

        # Move to the stand position and add a flash of light.
        spaz.handlemessage(
            StandMessage(
                position, angle if angle is not None else random.uniform(0, 360)
            )
        )
        self._spawn_sound.play(1, position=spaz.node.position)
        light = _bascenev1.newnode('light', attrs={'color': light_color})
        spaz.node.connectattr('position', light, 'position')
        animate(light, 'intensity', {0: 0, 0.25: 1, 0.5: 0})
        _bascenev1.timer(0.5, light.delete)
        return spaz

# ============================================================================
# 🔥 THE CRITICAL PATCH (THIS REPLACES multiteamvictory.py)
# ============================================================================

import bascenev1lib.activity.multiteamvictory as _mtv

_mtv.TeamSeriesVictoryScoreScreenActivity = MVPVsKillerScoreScreenActivity

print(
    "🔥 OVERRIDDEN: multiteamvictory.TeamSeriesVictoryScoreScreenActivity → "
    "MVPVsKillerScoreScreenActivity"
)
