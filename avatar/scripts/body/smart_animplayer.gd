class_name SmartAnimationPlayer extends AnimationPlayer

@export var body: AvatarBody

var formManager: FormManager = FormManager.new()
var isLoadingLibrary: bool = false

var currentForm: String:
	get: 
		if body: return body.currentForm
		return ""

var currentLocation: Vector2:
	get: 
		if body: return body.global_position
		return Vector2.ZERO

	set(v): body.global_position = v

var direction: Vector2:
	get:
		if body: return body.direction
		return Vector2.ZERO
	set(v): body.direction = v


var lastDirection: Vector2:
	get:
		if body: return body.lastDirection
		return Vector2.ZERO
	set(v): body.lastDirection = v

var isRunning: bool:
	get:
		if body: return body.isRunning
		return false
	
	set(v): body.isRunning = v

var isShifting: bool:
	get:
		if body: return body.isShifting
		return false

	set(v): body.isShifting = v

var isAttacking: bool:
	get:
		if body: return body.isAttacking
		return false

	set(v): body.isAttacking = v

var isCasting: bool:
	get:
		if body: return body.isCasting
		return false
	set(v): body.isCasting = v

func _physics_process(_delta: float) -> void:
	HandleAnimation()

func HandleAnimation() -> void:
	if isShifting: return
	if currentForm.is_empty(): return
	if isLoadingLibrary: return

	if not has_animation_library(currentForm):
		SwapLibrary(currentForm)
		return

	if direction.length_squared() < 0.01:
		
		if isCasting: return

		if isAttacking:
			HandleAttackAnimation()
			return

	HandleMovementAnimations()

func SwapLibrary(formName: String) -> void:
	isLoadingLibrary = true
	var library: AnimationLibrary = formManager.characterLibrary2D.get(formName, null)
	if library == null:
		isLoadingLibrary = false
		return

	for lib in get_animation_library_list():
		remove_animation_library(lib)

	add_animation_library(formName, library)

	var setupAnim = formName + "/Setup_Form"
	if has_animation(setupAnim):
		isShifting = true
		play(setupAnim)
		await animation_finished
		isShifting = false

	isLoadingLibrary = false

func HandleMovementAnimations() -> void:
	if direction.length_squared() > 0.01:
		if isRunning:
			Run(direction)
		else:
			Walk(direction)
	else:
		var idleDir: Vector2 = lastDirection if lastDirection.length_squared() > 0 else Vector2(0, 1)
		Idle(idleDir)

func HandleAttackAnimation() -> void:
	var dir: Vector2 = lastDirection if lastDirection.length_squared() > 0 else Vector2(0, 1)
	var animName: String = GetDirectionalAnimation("Attack", dir)
	if current_animation != animName:
		play(animName)

func Idle(dir: Vector2) -> void:
	var animName = GetDirectionalIdle(dir)
	if current_animation != animName:
		play(animName)

func Walk(dir: Vector2) -> void:
	var animName = GetDirectionalWalk(dir)
	if current_animation != animName:
		play(animName)

func Run(dir: Vector2) -> void:
	var animName: String = GetDirectionalAnimation("Run", dir)
	if current_animation != animName:
		play(animName)

func GetDirectionalWalk(dir: Vector2) -> String:
	return GetDirectionalAnimation("Walk", dir)

func GetDirectionalIdle(dir: Vector2) -> String:
	return GetDirectionalAnimation("Idle", dir)

func GetDirectionalAnimation(base: String, dir: Vector2) -> String:
	var prefix = currentForm + "/" + base
	var x = dir.x
	var y = dir.y
	const THRESHOLD = 1.1

	var candidates := []

	if abs(x) > THRESHOLD and abs(y) > THRESHOLD:
		if x > 0 and y > 0:      candidates = [prefix + "_Down_Right", prefix + "_Right", prefix + "_Down"]
		elif x > 0 and y < 0:    candidates = [prefix + "_Up_Right",   prefix + "_Right", prefix + "_Up"]
		elif x < 0 and y > 0:    candidates = [prefix + "_Down_Left",  prefix + "_Left",  prefix + "_Down"]
		else:                    candidates = [prefix + "_Up_Left",     prefix + "_Left",  prefix + "_Up"]
	else:
		if abs(x) > abs(y):
			candidates = [prefix + ("_Right" if x >= 0 else "_Left")]
		else:
			candidates = [prefix + ("_Down" if y >= 0 else "_Up")]

	for anim in candidates:
		if has_animation(anim):
			return anim

	return prefix if has_animation(prefix) else currentForm + "/Idle_Down"

func ShiftForm(newForm: String) -> void:
	if isShifting or currentForm == newForm or newForm == "":
		return
	
	#if not has_animation_library(newForm):
		#LoadForm(newForm)
	
	var shiftAnimName = MatchShiftAnimation(newForm)
	
	if has_animation(shiftAnimName):
		isShifting = true
		play(shiftAnimName)
		await animation_finished
		isShifting = false
	
	currentForm = newForm
	Idle(Vector2(0, 1))

func MatchShiftAnimation(form: String) -> String:
	match form:
		"Small Fox":      return "Small Fox/Fox_Form"
		"Anna":           return "Anna/Anna_Form"
		"Goblin Scout":   return "Goblin Scout/Goblin_Scout_Form"
		_:                return form + "/" + form.get_file().get_basename() + "_Form"

func ForceFormChange(newForm: String) -> void:
	currentForm = newForm
	isShifting = false
	Idle(Vector2(0, 1))

func PlayCustomAnimation(animationType: String) -> void:
	var baseName = currentForm + "/" + animationType
	var dir = lastDirection
	if dir == Vector2.ZERO:
		dir = Vector2(0, 1)
	
	var animName := ""
	
	match animationType:
		"Cast":
			animName = GetDirectionalCast(baseName)
		"Attack", "Hurt", "Death":
			animName = GetDirectionalAnimation(animationType, dir)
		_:
			animName = baseName

	if animName != "" and has_animation(animName):
		play(animName)
	#else:
		#push_warning("Missing animation: " + animName + " in form " + currentForm)

func GetDirectionalCast(baseName: String) -> String:
	var dir = lastDirection

	# Hard fallback
	if dir == Vector2.ZERO:
		dir = Vector2(1, 0)

	var rightAnim = baseName + "_Right"
	var leftAnim  = baseName + "_Left"

	if dir.x >= 0:
		if has_animation(rightAnim):
			return rightAnim
	elif has_animation(leftAnim):
		return leftAnim

	# Final safety fallback
	if has_animation(rightAnim):
		return rightAnim
	if has_animation(leftAnim):
		return leftAnim

	return ""

func Cast() -> void:    PlayCustomAnimation("Cast")
func Death() -> void:   PlayCustomAnimation("Death")
func Hurt() -> void:    PlayCustomAnimation("Hurt")

func GetCurrentForm() -> String:   return currentForm
func IsTransforming() -> bool:     return isShifting

#func LoadForm(formName: String) -> void:
	#var path: String = ""
	#for form in FormManager.animationLibrary.keys():
		#if FormManager.animForms.keys()[form] == formName:
			#path = FormManager.animationLibrary[form]
			#break
	#if path == "": return
	#var library: AnimationLibrary = load(path)
	#if library == null: return
	#if has_animation_library(formName):
		#remove_animation_library(formName)
	#add_animation_library(formName, library)
