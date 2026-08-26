class_name AvatarBody extends CharacterBody2D

## The rendering/movement shell for a desktop companion character. Deliberately
## has NO decision-making of its own - no wander timer, no utility-AI action
## scorer, no autonomous "what should I do" loop. Godot's job is to look like
## whoever's driving her and to relay input events back out; deciding what she
## wants is Python's job (modules/soul/ - mental_state/identity_state), once
## the bridge exists. Until then she just idles and waits for explicit
## move_to()/play()/say() calls (e.g. from a debug harness), the same
## contract the eventual Python bridge will use.
##
## Property names are camelCase to match smart_animplayer.gd (ported as-is
## from Autumn's Dungeoneering, which reads/writes body.isRunning,
## body.lastDirection etc. directly) rather than editing that reused file.

signal clicked(button_index: int)

@export var currentForm: String = "Tama"
@export var moveSpeed: float = 120.0

var direction: Vector2 = Vector2.ZERO
var lastDirection: Vector2 = Vector2(0, 1)
var isRunning: bool = false
var isShifting: bool = false
var isAttacking: bool = false
var isCasting: bool = false

var _target: Vector2 = Vector2.ZERO
var _hasTarget: bool = false

func move_to(target_position: Vector2, running: bool = false) -> void:
	_target = target_position
	_hasTarget = true
	isRunning = running

func stop() -> void:
	_hasTarget = false
	direction = Vector2.ZERO

func _physics_process(_delta: float) -> void:
	if not _hasTarget:
		direction = Vector2.ZERO
		return

	var to_target: Vector2 = _target - global_position
	if to_target.length() < 4.0:
		_hasTarget = false
		direction = Vector2.ZERO
		velocity = Vector2.ZERO
		return

	direction = to_target.normalized()
	lastDirection = direction
	velocity = direction * (moveSpeed * (2.0 if isRunning else 1.0))
	move_and_slide()

func _on_click_area_input_event(_viewport: Node, event: InputEvent, _shape_idx: int) -> void:
	if event is InputEventMouseButton and event.pressed:
		clicked.emit(event.button_index)
