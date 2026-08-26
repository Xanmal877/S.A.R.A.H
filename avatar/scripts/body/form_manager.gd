class_name FormManager extends Node

## Trimmed down from Autumn's Dungeoneering's visual/animation_logic/form_manager.gd.
## AD's version preloads a whole adventurer roster by uid://, most of which
## doesn't exist in this project. Loaded by explicit res:// path instead of
## uid:// since we only carry the one asset (Tama) over, not AD's full
## uid cache.

const TAMA_ANIMATION: AnimationLibrary = preload("res://visual/animation_logic/animations/Tama.res")

var characterLibrary2D: Dictionary = {
	"Tama": TAMA_ANIMATION,
}
