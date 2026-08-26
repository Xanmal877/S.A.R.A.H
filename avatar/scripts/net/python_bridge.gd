class_name PythonBridge extends Node

## Client side of modules/avatar/avatar_bridge.py's newline-delimited JSON
## protocol. This node only ever does two things: (1) turn incoming "cmd"
## messages into calls on the AvatarBody/Main it's given, and (2) forward
## her signals out as "event" messages. It makes no decisions of its own -
## see avatar_body.gd's header for why that split matters.
##
## Connects OUT to Python (the long-lived side, a systemd service) rather
## than listening itself, and retries on a short timer if Python isn't up
## yet or drops - the avatar process is expected to come and go independently.

const HOST := "127.0.0.1"
const PORT := 8791
const RECONNECT_INTERVAL := 2.0

@export var avatar: AvatarBody
@export var main: Node  # expected to expose show_speech(text: String)

var _socket: StreamPeerTCP = StreamPeerTCP.new()
var _connected: bool = false
var _reconnect_timer: float = 0.0
var _recv_buffer: String = ""

func _ready() -> void:
	if is_instance_valid(avatar):
		avatar.clicked.connect(_on_avatar_clicked)
	_try_connect()

func _process(delta: float) -> void:
	_socket.poll()
	var status := _socket.get_status()

	if status == StreamPeerTCP.STATUS_CONNECTED:
		if not _connected:
			_connected = true
			print("[PythonBridge] Connected to ", HOST, ":", PORT)
		_read_available()
	else:
		if _connected:
			print("[PythonBridge] Disconnected")
		_connected = false
		_reconnect_timer -= delta
		if _reconnect_timer <= 0.0:
			_try_connect()

func _try_connect() -> void:
	_reconnect_timer = RECONNECT_INTERVAL
	_socket = StreamPeerTCP.new()
	_socket.connect_to_host(HOST, PORT)

func _read_available() -> void:
	var n := _socket.get_available_bytes()
	if n <= 0:
		return
	var chunk := _socket.get_utf8_string(n)
	_recv_buffer += chunk
	while true:
		var idx := _recv_buffer.find("\n")
		if idx == -1:
			break
		var line := _recv_buffer.substr(0, idx)
		_recv_buffer = _recv_buffer.substr(idx + 1)
		_handle_line(line)

func _handle_line(line: String) -> void:
	if line.strip_edges().is_empty():
		return
	var parsed = JSON.parse_string(line)
	if typeof(parsed) != TYPE_DICTIONARY or parsed.get("type") != "cmd":
		return

	var name: String = parsed.get("name", "")
	var args: Dictionary = parsed.get("args", {})

	match name:
		"move_to":
			if is_instance_valid(avatar):
				avatar.move_to(Vector2(args.get("x", 0.0), args.get("y", 0.0)), args.get("running", false))
		"play":
			if is_instance_valid(avatar):
				var anim_player := avatar.get_node_or_null("SmartAnimationPlayer")
				if anim_player:
					anim_player.PlayCustomAnimation(args.get("animation", ""))
		"say":
			if is_instance_valid(main) and main.has_method("show_speech"):
				main.show_speech(args.get("text", ""))
		_:
			print("[PythonBridge] Unknown command: ", name)

func _on_avatar_clicked(button_index: int) -> void:
	_send_event("clicked", {"button": button_index})

func _send_event(name: String, args: Dictionary) -> void:
	if _socket.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		return
	var payload := JSON.stringify({"type": "event", "name": name, "args": args}) + "\n"
	_socket.put_utf8_string(payload)
