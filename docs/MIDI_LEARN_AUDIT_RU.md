# Аудит MIDI Learn — Auricle v2.0.0

Дата: 1 ноября 2026 года.

Исходный комплект: `Auricle-v2.0.0-full-distribution(1).zip`.
SHA-256 исходного архива: `fc2415e21bcdb0e0974e3c1412ef69f3edf422e8985fc44aa39f69769336125b`.

## Область проверки

Проверена цепочка получения MIDI IN, контекстных меню Learn, регистрации
привязок, soft takeover (Pickup), доставки изменений через Transport Command
Queue, обновления интерфейса, сохранения/загрузки и смены проекта.
Дополнительно просмотрены взаимодействия с Drum Kit, HistoryController и
ParameterInfluence. Это целевой аудит MIDI Learn и связанных компонентов,
а не утверждение об отсутствии ошибок во всём приложении.

## Найденные дефекты и исправления

| Важность | Дефект исходной реализации | Исправление |
| --- | --- | --- |
| Блокирующий для первого подключения | В новом проекте Connect отключён. Выбор устройства не включает кнопку: отсутствовала обработка смены индекса списка MIDI Input. | Выбор входа немедленно обновляет состояние действий. |
| Высокая | Постоянные ручки Drum Kit заново подключались к Learn/Clear при каждом обновлении Inspector. После трёх обновлений одна ручка имела четыре обработчика. | Каждая ручка подключается один раз за своё время жизни. |
| Высокая | После ошибки reader thread имя входа оставалось активным. Повторное подключение того же имени ошибочно считалось успешным без нового reader. | Ошибка доставляется в GUI, сбрасывает подключение и показывает причину. Повторное подключение проверяет работоспособность reader. |
| Высокая | Уже поставленные в очередь события предыдущего подключения принимались после его закрытия, в том числе при повторном открытии того же устройства. | Каждому подключению назначается отдельный идентификатор; устаревшие события и ошибки отбрасываются. |
| Высокая | При смене проекта с тем же MIDI-входом сохранялась старая очередь событий. | Старый вход отключается до смены модели; новый проект получает новую сессию входа. |
| Высокая | Pickup применялся к Note On. Кнопка с постоянной velocity 127 не могла пересечь, например, текущее значение 0.5, поэтому параметр не реагировал. | Новые Note-привязки создаются без Pickup. Для существующих привязок Pickup можно переключить в менеджере. |
| Высокая | Pickup сравнивал сырое значение контроллера с уже преобразованной величиной для кривых exp/smooth. | Пересечение и близость проверяются после применения кривой, в той же системе значений, что и параметр. |
| Высокая | Pickup ориентировался на эффективное значение параметра, которое могло постоянно изменяться автоматическими слоями. | Подхват ориентируется на исходное ручное значение. Сами политики влияний сохраняются: MIDI не принуждает автоматические слои отключаться. |
| Средняя | Колонка Pickup показывала только текст; штатного переключения не было. | Добавлен рабочий checkbox Pickup. При переключении Pickup/Enabled состояние подхвата сбрасывается. |
| Средняя | При выключении и повторном включении привязки сохранялось уже захваченное состояние Pickup. | После повторного включения снова требуется подхват, если Pickup включён. |
| Средняя | Reader закрывался из GUI после ограниченного ожидания потока; это допускало одновременное чтение/закрытие. | Открытый вход закрывает владеющий им reader в finally после завершения чтения. |
| Средняя | Закрытый порт мог бесконечно опрашиваться. Полное преобразование iter_pending в список откладывало проверку Stop до конца очереди. | Проверяются закрытие порта и Stop внутри пакета сообщений. |
| Средняя | Можно было сохранить привязку к блоку/голосу, удалённому во время ожидания Learn. | Удалённая цель отменяет обучение без создания неработающей привязки. |
| Средняя | Обновление таблицы могло заменять её элементы прямо внутри itemChanged. | Обновление откладывается до завершения текущего Qt-события. |
| Низкая | Закрытые модальные менеджеры оставались дочерними объектами окна и продолжали получать сигналы входа. | После закрытия менеджер удаляется через deleteLater. |
| Низкая | Отсутствовала явная отмена ожидания Learn; при добавлении новых привязок не проверялся лимит хранения. | Добавлены Cancel Learn и проверка лимита 512 привязок. |

## Проверки

- В исходном комплекте существующие 15 тестов MIDI Learn/Input проходили.
- Из первых 12 добавленных сценариев на исходном коде падали 11. Они
  воспроизводили дефекты подключения, повторных обработчиков, Pickup,
  устаревших событий, ошибки reader и удалённой цели.
- Добавлены 23 проверки с настоящими QApplication, MainWindow, элементами
  управления, queued signals и тестовым портом на базе Mido BaseInput.
- Все 23 новые проверки пройдены на Python 3.12.14 / Qt 6.12.0 / Mido 1.3.3.
- Проверены Learn из контекстного меню при активном HistoryController,
  глобальный макрос с обновлением слайдера, целочисленный параметр Drum
  Voice, серия 128 CC-сообщений, закрытие входа, переподключение,
  сохранение привязок и смена проекта.
- Python-компиляция изменённых модулей успешна.

Отдельно пройден сценарий с настоящим модальным exec(): Learn без
подключённого входа → выбор порта → Connect → получение CC → регистрация
привязки → закрытие и удаление менеджера.

### Полный сравнительный прогон

| Вариант | Всего тестов | Пройдено | Не пройдено |
| --- | ---: | ---: | ---: |
| Исходный архив | 2052 | 1921 | 131 |
| Исправленный код + новые тесты | 2075 | 1944 | 131 |

Списки идентификаторов 131 падающего теста в обоих прогонах полностью
совпадают. Новых падающих тестов не появилось. Полный набор при этом
не является зелёным: эти 131 исходных сбоя не исправлялись в данном
патче MIDI Learn.

Часть сбоев связана с несогласованностью старых тестов и текущего API
очереди редактирования: 24 проверки завершаются отсутствием
`_mark_pending_dirty` у тестового `_Host`, ещё 7 обращаются к отсутствующему
`MainWindow._kit_regen_pending`. Это не позволяет считать все 131 сбой
ошибками пользовательского выполнения; остальные требуют отдельного
разбора. Есть непройденные проверки Composition, длины паттернов,
inline-редакторов, истории, жизненного цикла Kit Preview и других областей.

Основные группы по количеству падающих тестов:

| Модуль тестов | Количество |
| --- | ---: |
| test_composition_planner_ui | 22 |
| test_pattern_length_ui | 10 |
| test_inline_editors | 9 |
| test_kit_preview_lifecycle | 8 |
| test_composition_automation_ui | 7 |
| test_history_influence_harmony | 7 |

Числа относятся к этим двум запускам на одной конфигурации среды.
Старые результаты проверки, вложенные в исходную поставку, не заменяют
проверку фактически приложенного кода.

## Ограничения проверки

Физический MIDI-контроллер и его драйвер не подключались. Вместо них
использовался Mido BaseInput с реальной очередью сообщений и фоновым
чтением; Qt-интерфейс и доставка сигналов работали штатно в offscreen.
Это проверка программной цепочки, а не аппаратная сертификация.

Поддержка относительных энкодеров, NRPN/RPN и 14-bit CC не добавлялась.
Существующий CC Learn трактует Control Change как абсолютное значение
0–127. Сообщения clock и note_off не используются для обучения; Note On
управляет значением через velocity, а не переключает параметр On/Off.

Сохранены модель проекта, MIDI Expression/Sync, оформление, музыкальные
алгоритмы и сохранённый профиль algo_conf. Изменения схемы файлов проекта
не требуются.

## Проверенные первоисточники

- Mido, Input / Callbacks: https://mido.readthedocs.io/en/latest/ports/
- Mido, RtMidi backend / thread safety: https://mido.github.io/mido/backends/rtmidi.html

Polling через iter_pending сохранён. Обнаруженные UI/runtime-дефекты не
требуют предположения, что callback сам по себе не поддерживается Mido.

## Исходные непройденные проверки (одинаковый список в обоих прогонах)

- `tests.test_composition_automation_ui::test_curve_controls_keep_project_points_and_emit_silent_runtime_updates`
- `tests.test_composition_automation_ui::test_curve_mouse_and_keyboard_edit_endpoints_and_interior_points`
- `tests.test_composition_automation_ui::test_editing_future_section_never_releases_current_notes[False]`
- `tests.test_composition_automation_ui::test_editing_future_section_never_releases_current_notes[True]`
- `tests.test_composition_automation_ui::test_expression_selection_changes_only_selected_entity_and_hides_irrelevant_pitch_controls`
- `tests.test_composition_automation_ui::test_future_section_edit_preserves_actual_active_midi_note_then_current_edit_sends_note_off`
- `tests.test_composition_automation_ui::test_one_curve_drag_is_one_undo_redo_step_and_duplicates_are_independent`
- `tests.test_composition_planner_ui::test_add_duplicate_reorder_remove_and_per_block_edit_persist_to_project`
- `tests.test_composition_planner_ui::test_compact_layout_keeps_timeline_clear_and_captions_next_to_fields[size0]`
- `tests.test_composition_planner_ui::test_compact_layout_keeps_timeline_clear_and_captions_next_to_fields[size1]`
- `tests.test_composition_planner_ui::test_compact_layout_keeps_timeline_clear_and_captions_next_to_fields[size2]`
- `tests.test_composition_planner_ui::test_composition_tab_has_all_eight_types_and_individual_drum_voice_rows`
- `tests.test_composition_planner_ui::test_drag_reorder_is_one_undo_redo_edit`
- `tests.test_composition_planner_ui::test_enabling_composition_regenerates_source_without_density_pruning`
- `tests.test_composition_planner_ui::test_internal_drag_move_preserves_selected_section_and_its_settings`
- `tests.test_composition_planner_ui::test_name_duration_edits_refresh_full_form_and_selected_timeline_section`
- `tests.test_composition_planner_ui::test_selected_section_text_is_visible_in_every_theme[Blue Hour]`
- `tests.test_composition_planner_ui::test_selected_section_text_is_visible_in_every_theme[Cloud]`
- `tests.test_composition_planner_ui::test_selected_section_text_is_visible_in_every_theme[Espresso]`
- `tests.test_composition_planner_ui::test_selected_section_text_is_visible_in_every_theme[Graphite]`
- `tests.test_composition_planner_ui::test_selected_section_text_is_visible_in_every_theme[Lavender]`
- `tests.test_composition_planner_ui::test_selected_section_text_is_visible_in_every_theme[Pine]`
- `tests.test_composition_planner_ui::test_selected_section_text_is_visible_in_every_theme[Porcelain]`
- `tests.test_composition_planner_ui::test_selected_section_text_is_visible_in_every_theme[Sage]`
- `tests.test_composition_planner_ui::test_selected_section_text_is_visible_in_every_theme[Sand]`
- `tests.test_composition_planner_ui::test_selected_section_text_is_visible_in_every_theme[Soft Plum]`
- `tests.test_composition_planner_ui::test_total_length_and_timeline_use_whole_form_meter_and_bpm[4/4-48-0:24]`
- `tests.test_composition_planner_ui::test_total_length_and_timeline_use_whole_form_meter_and_bpm[6/8-36-0:18]`
- `tests.test_composition_planner_ui::test_total_length_and_timeline_use_whole_form_meter_and_bpm[7/8-42-0:21]`
- `tests.test_composition_playback_ui::test_composition_icons_follow_the_same_dark_light_contrast_rule[Solar-True]`
- `tests.test_composition_playback_ui::test_end_choice_is_persistent_and_undo_redo_updates_the_widget`
- `tests.test_coordinated_kit::test_pinned_configuration_role_switch_and_knob_edits_survive_ui_refresh`
- `tests.test_cross_system_interactions::test_ui_mode_or_algorithm_edit_leaves_other_performance_running[card]`
- `tests.test_drum_rhythm_ui::test_add_edits_and_removes_a_coloured_inline_link_without_dialog`
- `tests.test_drum_rhythm_ui::test_musical_kit_and_inline_links_participate_in_undo_redo`
- `tests.test_drum_rhythm_ui::test_one_click_enables_all_three_directions_and_keeps_the_kit_pinned`
- `tests.test_drum_rhythm_ui::test_rhythm_map_pad_and_presets_update_the_existing_map_parameters`
- `tests.test_history_influence_harmony::test_auto_values_do_not_undo_with_a_later_manual_edit`
- `tests.test_history_influence_harmony::test_compact_header_controls_do_not_overlap`
- `tests.test_history_influence_harmony::test_delete_undo_restores_routes_and_entire_drum_kit`
- `tests.test_history_influence_harmony::test_gui_one_drag_is_one_undo_and_value_click_opens_card`
- `tests.test_history_influence_harmony::test_gui_plan_edit_undo_and_playing_undo_preserves_position`
- `tests.test_history_influence_harmony::test_gui_undo_redo_complete_document_and_savepoint`
- `tests.test_history_influence_harmony::test_recovery_ui_restores_unsaved_copy_without_overwriting_saved_file`
- `tests.test_history_performance::test_fast_undo_stops_active_technique_without_restarting_it`
- `tests.test_history_performance::test_parameter_undo_keeps_controls_and_their_model_bindings[kit]`
- `tests.test_history_performance::test_parameter_undo_keeps_controls_and_their_model_bindings[macro]`
- `tests.test_history_performance::test_parameter_undo_keeps_controls_and_their_model_bindings[voice]`
- `tests.test_inline_editors::test_drum_mutator_target_does_not_offer_pitch`
- `tests.test_inline_editors::test_loaded_incompatible_mutator_is_visible_but_bypassed`
- `tests.test_inline_editors::test_mutator_add_type_target_and_amount_in_place[BASS]`
- `tests.test_inline_editors::test_mutator_add_type_target_and_amount_in_place[CHORD]`
- `tests.test_inline_editors::test_mutator_add_type_target_and_amount_in_place[DRUM]`
- `tests.test_inline_editors::test_mutator_add_type_target_and_amount_in_place[MELODY]`
- `tests.test_inline_editors::test_mutator_add_type_target_and_amount_in_place[PAD]`
- `tests.test_inline_editors::test_mutator_and_process_add_to_the_selected_drum_voice`
- `tests.test_inline_editors::test_mutator_choices_follow_data_types_and_preserve_the_editor`
- `tests.test_inspector_runtime_ui::test_inspector_scroll_reaches_bottom_for_drum_voice_and_other_block`
- `tests.test_instrument_dialogue::test_inline_dialogue_controls_history_copy_remove_and_narrow_layout`
- `tests.test_kit_controls::test_kit_knobs_update_sound_without_rebuilding_editor`
- `tests.test_kit_groove_fix::test_auto_roles_repairs_saved_perc_misclassification_without_changing_routing`
- `tests.test_kit_preview_lifecycle::test_knobs_work_with_parent_kit_selected[kit_density-0.0]`
- `tests.test_kit_preview_lifecycle::test_knobs_work_with_parent_kit_selected[kit_fill-1.0]`
- `tests.test_kit_preview_lifecycle::test_knobs_work_with_parent_kit_selected[kit_humanize-0.8]`
- `tests.test_kit_preview_lifecycle::test_pending_kit_edit_survives_inspector_replacement[empty]`
- `tests.test_kit_preview_lifecycle::test_pending_kit_edit_survives_inspector_replacement[kit]`
- `tests.test_kit_preview_lifecycle::test_pending_kit_edit_survives_inspector_replacement[melody]`
- `tests.test_kit_preview_lifecycle::test_pending_kit_edit_survives_inspector_replacement[voice]`
- `tests.test_kit_preview_lifecycle::test_project_switch_during_pending_kit_edit`
- `tests.test_kit_variations::test_controls_round_trip_and_grid_updates_in_place_without_deleting_the_inspector`
- `tests.test_kit_workflow::test_paste_and_undo_keep_target_mode_and_routing_and_do_not_restart_transport`
- `tests.test_kit_workflow::test_probability_editor_updates_steps_without_rebuilding_and_round_trips`
- `tests.test_motif_development_ui::test_capture_and_save_variant_create_selectable_themes`
- `tests.test_motif_development_ui::test_drum_voice_capture_does_not_change_siblings_or_pinned_selection`
- `tests.test_motif_development_ui::test_edits_hold_and_recall_keep_current_inspector_and_announce_boundary`
- `tests.test_motif_development_ui::test_transform_controls_create_a_non_destructive_library_child`
- `tests.test_motif_inspector::test_drum_voice_binding_keeps_kit_section_stable`
- `tests.test_motif_inspector::test_select_step_and_disable_motif_in_current_inspector`
- `tests.test_parameter_layers::test_influence_controls_save_undo_redo_and_keep_dialog_bound_to_current_engine`
- `tests.test_parameter_sources_ui::test_global_macro_and_kit_voice_markers_follow_composition_and_engine_replacement`
- `tests.test_pattern_length_ui::test_generator_preview_matches_rhythm_and_edit_converts_one_step`
- `tests.test_pattern_length_ui::test_length_updates_all_voices_and_clamps_visible_page`
- `tests.test_pattern_length_ui::test_plan_output_pages_follow_length_across_bars_and_phrases[2/4-128-1]`
- `tests.test_pattern_length_ui::test_plan_output_pages_follow_length_across_bars_and_phrases[4/4-32-1]`
- `tests.test_pattern_length_ui::test_plan_output_pages_follow_length_across_bars_and_phrases[5/4-64-2]`
- `tests.test_pattern_length_ui::test_plan_output_pages_follow_length_across_bars_and_phrases[7/8-32-1]`
- `tests.test_pattern_length_ui::test_shortening_keeps_hidden_tail_and_page_2_edits_absolute_step`
- `tests.test_pattern_length_ui::test_source_length_and_meter_are_independent_in_seq_and_live`
- `tests.test_pattern_length_ui::test_source_preview_updates_in_place_when_generator_parameters_change`
- `tests.test_pattern_length_ui::test_step_32_preserves_fractions_chances_and_undo`
- `tests.test_phrase_duration::test_phrase_ui_duration_controls_runtime_and_survives_save`
- `tests.test_playback_modes_ui::test_explicit_perform_start_starts_phrase_without_composition_or_main_play`
- `tests.test_playback_modes_ui::test_saved_enabled_technique_is_not_restarted_by_card_rebuild`
- `tests.test_register_center_ui::test_register_center_section_edit_participates_in_undo_redo`
- `tests.test_theme_switch_ui::test_existing_and_new_dialogs_inherit_window_theme`
- `tests.test_theme_switch_ui::test_theme_keeps_controls_playback_and_history`
- `tests.test_ui_refresh_cost::test_busy_worker_cannot_block_ui_refresh`
- `tests.test_unified_composition_ui::test_custom_color_duplicate_drag_and_roundtrip_preserve_identity`
- `tests.test_unified_composition_ui::test_fit_updates_on_meter_duration_and_custom_beats_stay_saved`
- `tests.test_unified_composition_ui::test_manual_audition_is_explicit_and_switches_from_form`
- `tests.test_unified_composition_ui::test_section_specific_phrase_technique_and_coefficients_undo_redo`
- `tests.test_v101_help_color_mute::test_mute_is_available_in_blocks_and_perform_and_shared`
- `tests.test_v102_1_ui::test_perform_card_turns_off_when_gesture_finishes`
- `tests.test_v102_1_ui::test_theme_switch_updates_application_palette`
- `tests.test_v102_1_ui::test_timeline_and_stage_strip_follow_phrase_state`
- `tests.test_v104_stability_fixes::test_editing_actions_mark_project_dirty`
- `tests.test_v105_source_geometry::test_inspector_reflows_after_final_viewport_geometry`
- `tests.test_v107_pad_chord_midi_channel_sync::test_channel_setter_syncs_visible_card_immediately`
- `tests.test_v55_inspector_regressions::test_inspector_refresh_keeps_geometry_pass_but_no_page_swap`
- `tests.test_v56_gui_regressions::test_parameter_regeneration_is_deferred`
- `tests.test_v58_inspector_spec::test_targeted_scroll_restore_uses_stable_group_identity`
- `tests.test_v60_relations_graph::test_duplicate_delete_and_stale_callbacks_keep_the_right_relation`
- `tests.test_v61_relations_labels::test_block_colours_and_names_refresh_in_both_endpoint_lists`
- `tests.test_v65_gui_audit::test_midi_inspector_updates_without_active_block_list_rebuild`
- `tests.test_v71_block_type_lifecycle::test_block_type_change_is_deferred_and_coalesced`
- `tests.test_v71_qt_lifecycle::test_algorithm_change_coalesces_rapid_combo_changes`
- `tests.test_v71_qt_lifecycle::test_algorithm_change_is_deferred_outside_combobox_callback`
- `tests.test_v71_qt_lifecycle::test_process_type_change_is_deferred_outside_combobox_callback`
- `tests.test_v72_qt_change_lifecycle::test_card_callbacks_do_not_destroy_the_emitting_card_synchronously`
- `tests.test_v72_qt_change_lifecycle::test_destructive_inspector_actions_use_queued_refresh`
- `tests.test_v72_qt_change_lifecycle::test_inspector_parameter_changes_do_not_rebuild_synchronously`
- `tests.test_v72_qt_change_lifecycle::test_inspector_refresh_is_queued_for_channel_and_note_changes`
- `tests.test_v72_qt_change_lifecycle::test_mode_change_is_deferred`
- `tests.test_v74_relations_editor::test_add_relation_immediately_creates_an_editable_row`
- `tests.test_v77_relation_inspector::test_inline_relations_persist_all_fields`
- `tests.test_v77_relation_inspector::test_relation_fields_update_model_and_output_without_rebuilding`
- `tests.test_v79_relation_ux::test_filter_add_and_empty_state`
- `tests.test_v84_themes::test_theme_catalog_contains_reference_and_new_themes`
- `tests.test_v86_relation_layout::test_new_relation_scrolls_into_view_and_mutator_knob_fits`
- `tests.test_v87_help::test_all_generator_and_process_catalog_entries_are_documented`
- `tests.test_v89_logo::test_logo_keeps_its_original_colours_on_light_and_dark_themes`
