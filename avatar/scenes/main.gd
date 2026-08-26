extends Node

## Desktop shell: transparent/borderless/always-on-top window + click-through
## passthrough. The window-transparency/click-through-to-desktop mechanics
## here are carried over from origin/godot-desktop's main.gd (that part
## worked, verified live under KDE/XWayland). What's NEW is the passthrough
## polygon also carving out a notch around the avatar's own body - the old
## branch only ever punched a hole for its fixed chat-toggle button, so
## clicking directly on her did nothing at all. No utility-AI/wander-timer
## here on purpose - see avatar_body.gd's header comment. Interaction below
## (M to walk to a random point, click to react) is a manual debug harness,
## not real behavior; real behavior comes from Python once the bridge exists.

const AvatarBodyScene := preload("res://scenes/avatar_body_tama.tscn")
const CLICK_HALF_SIZE := Vector2(75, 95)  # matches ClickShape in avatar_body_tama.tscn

var avatar: AvatarBody
var reaction_label: Label

func _ready() -> void:
	get_tree().root.transparent_bg = true
	get_viewport().transparent_bg = true
	RenderingServer.set_default_clear_color(Color(0, 0, 0, 0))

	var screen := DisplayServer.screen_get_size()

	avatar = AvatarBodyScene.instantiate()
	avatar.global_position = Vector2(screen.x / 2.0, screen.y / 2.0)
	avatar.clicked.connect(_on_avatar_clicked)
	add_child(avatar)

	reaction_label = Label.new()
	reaction_label.visible = false
	reaction_label.add_theme_color_override("font_color", Color.WHITE)
	reaction_label.add_theme_font_size_override("font_size", 16)
	reaction_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	reaction_label.custom_minimum_size = Vector2(120, 0)
	var canvas := CanvasLayer.new()
	add_child(canvas)
	canvas.add_child(reaction_label)

	print("[Avatar] Ready. Press M to send her to a random point (manual test only).")

func _process(_delta: float) -> void:
	_update_passthrough()
	if reaction_label.visible:
		# Label position is its top-left corner, not its center - offset by
		# half its own width to actually center it over her, and clear a
		# full head's height (she's 3x-scaled, ~190px tall) above her pivot.
		var screen_pos := avatar.global_position - Vector2(reaction_label.custom_minimum_size.x / 2.0, 100)
		reaction_label.position = screen_pos

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_M:
		var screen := DisplayServer.screen_get_size()
		var target := Vector2(randf_range(64, screen.x - 64), randf_range(64, screen.y - 64))
		print("[Avatar] Manual test: walking to ", target)
		avatar.move_to(target)

func _on_avatar_clicked(button_index: int) -> void:
	print("[Avatar] Clicked with button ", button_index)
	reaction_label.text = "Hey!" if button_index == MOUSE_BUTTON_LEFT else "..."
	reaction_label.visible = true
	var timer := get_tree().create_timer(1.5)
	timer.timeout.connect(func(): reaction_label.visible = false)

func _update_passthrough() -> void:
	if not is_instance_valid(avatar):
		DisplayServer.window_set_mouse_passthrough(PackedVector2Array())
		return

	var center: Vector2 = avatar.global_position
	var top_left: Vector2 = center - CLICK_HALF_SIZE
	var bottom_right: Vector2 = center + CLICK_HALF_SIZE

	var poly := PackedVector2Array([
		Vector2(top_left.x, top_left.y),
		Vector2(bottom_right.x, top_left.y),
		Vector2(bottom_right.x, bottom_right.y),
		Vector2(top_left.x, bottom_right.y),
	])
	DisplayServer.window_set_mouse_passthrough(poly)
