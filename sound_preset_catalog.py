"""Musical starting points; every factory setting is an ordinary editable preset."""
from copy import deepcopy
from dataclasses import asdict
from functools import lru_cache

from auricle_catalogs import GENERATORS, ROLE_PROFILES
from auricle_model import Block, make_default_drum_voices
from sound_presets import FORMAT, VERSION, algorithm_defaults, validate

# Name, musical purpose, explicit deviations from the engine defaults.
ALGORITHMS = {
 'Euclidean': [('Five in sixteen','Balanced five-hit cycle.',{'pulses':5}), ('Tresillo','Three evenly distributed hits in eight steps.',{'euclidean_steps':8,'pulses':3}), ('Rotated seven','Dense displaced sixteen-step rhythm.',{'pulses':7,'euclidean_rotation':3})],
 'Bresenham': [('Five pulses','Distributed five-hit rhythm.',{'bres_pulses':5}),('Sparse three','Three hits in sixteen steps.',{'bres_pulses':3}),('Offset nine','Dense nine-hit rhythm, shifted by two steps.',{'bres_pulses':9,'bres_rotation':2})],
 'Polyrhythm': [('Three over four','Union of three- and four-step cycles.',{}),('Five against seven','Two longer, offset cycles.',{'poly_a':5,'poly_b':7,'poly_phase_b':2}),('Interlocking','Only noncoincident events of three and four.',{'poly_mode':'XOR'})],
 'Thue-Morse': [('Binary balance','Full binary self-similar rhythm.',{}),('Negative space','Inverted sequence.',{'tm_invert':True}),('Sparse fractal','Retain roughly half the active cells.',{'tm_density':.5,'variation_seed':13})],
 'Fibonacci Rhythm': [('Balanced','Moderate Fibonacci rhythm density.',{}),('Sparse','Lighter rhythm with a displaced origin.',{'fib_density':.3,'fib_offset':2}),('Busy','Denser Fibonacci accents.',{'fib_density':.8})],
 'Fibonacci': [('Diatonic cycle','Seven-degree sequence.',{}),('Wide stride','Leap through twelve degrees.',{'sequence_mod':12,'sequence_stride':3}),('Reverse answer','Reverse contour with a two-degree offset.',{'sequence_reverse':True,'sequence_offset':2})],
 'Recaman': [('Diatonic return','Seven-degree Recaman contour.',{}),('Broad register','Wider modular contour.',{'sequence_mod':14,'sequence_stride':2}),('Mirror response','Reverse the modular sequence.',{'sequence_reverse':True,'sequence_offset':3})],
 'De Bruijn': [('Order three','Binary rhythm with three-event memory.',{}),('Long rhythm','Order-five rhythm, rotated.',{'debruijn_order':5,'debruijn_rotation':3}),('Pitch traversal','Use the sequence as scale degrees.',{'debruijn_mode':'Pitch','debruijn_order':3})],
 'Markov': [('Close motion','Small jumps with repeated notes.',{'markov_jump':2,'markov_stay':.3,'markov_leap':.03}),('Breathing phrase','Occasional rests and moderate leaps.',{'markov_rest':.2,'markov_leap':.15}),('Wide gestures','Broader jumps across an octave.',{'markov_jump':6,'markov_octaves':1,'markov_leap':.35})],
 'Random Walk': [('Returning line','Short steps with a strong return bias.',{'walk_step':1,'walk_return_bias':.65}),('Rising drift','Gentle upward drift in a wider range.',{'walk_drift':.35,'walk_range':24}),('Restless','Larger steps and little attraction to the center.',{'walk_step':5,'walk_range':36,'walk_return_bias':.05})],
 'Interval Walker': [('Small steps','One-step movement with frequent return.',{'interval_step':1,'interval_return':.5,'interval_leap':.02}),('Thirds','Interval-three movement in the scale.',{}),('Angular','Larger interval and greater leap chance.',{'interval_step':7,'interval_range':36,'interval_leap':.3})],
 'Scale Walker': [('Stepwise','Single-degree motion with few leaps.',{'scale_leap':.02,'scale_octaves':1}),('Rising','Predominantly upward movement.',{'scale_direction':.8,'scale_octaves':3}),('Leaping','Two-degree steps and more occasional leaps.',{'scale_step':2,'scale_leap':.3})],
 'Weighted Scale': [('Tonic anchor','Favor root and fifth degrees of a seven-note scale.',{'scale_weights':'5,1,2,1,4,1,2'}),('Even field','All scale degrees have equal weight.',{}),('Upper color','Favor upper degrees with octave spread.',{'scale_weights':'1,1,2,2,2,4,4','scale_octave_spread':.45})],
 'Arpeggiator': [('Triad up','Root, third and fifth in ascending order.',{'arp_pattern':'0,2,4'}),('Two-octave wave','Seventh arpeggio with alternating direction.',{'arp_octaves':2,'arp_direction':'Up/Down'}),('Falling open','Descending pattern with wide degree spacing.',{'arp_pattern':'0,4,8','arp_direction':'Down','arp_octaves':2})],
 'Probability': [('Sparse','Quarter of events retained.',{'probability':.25,'probability_pitch_range':5}),('Balanced','Moderate probability and pitch range.',{}),('Active','High activity and broader pitch field.',{'probability':.85,'probability_pitch_range':12,'probability_octaves':1})],
 'Pattern': [('Four on floor','One hit per quarter note on the sixteenth grid.',{'pattern':'1,0,0,0'}),('Offbeats','Two attacks separated by uneven gaps.',{'pattern':'0,0,1,0,0,0,1,0'}),('Broken accents','Asymmetric sixteen-step accent pattern.',{'pattern':'1,0,0,.5,0,0,.8,0,1,0,.4,0,0,.7,0,0'})],
 'Cellular Automaton': [('Rule thirty','Classic Rule 30 with wrap boundary.',{}),('Rule ninety','Symmetric branching, viewed as an evolution trail.',{'ca_rule':90,'ca_generations':4,'ca_evolution':'Evolution Trail'}),('Pitch cells','Cell states shape a pitch sequence.',{'ca_rule':110,'ca_mode':'Pitch','ca_generations':5})],
 'L-System': [('Fibonacci grammar','AB/A rewrite mapped to scale degrees.',{}),('Branching melody','Turtle pitch with explicit turns.',{'ls_axiom':'A','ls_rule_a':'A+B','ls_rule_b':'A-B','ls_mode':'Turtle Pitch','ls_iterations':4}),('Rhythmic grammar','AB/A grammar mapped to rhythmic events.',{'ls_mode':'Rhythm','ls_iterations':5})],
 'Logistic Chaos': [('Stable orbit','Low R produces a restrained periodic orbit.',{'chaos_r':3.2,'chaos_burn_in':64,'chaos_octaves':1}),('Edge of chaos','More varied motion with modest smoothing.',{'chaos_r':3.57,'chaos_burn_in':128,'chaos_smooth':.2}),('Turbulent','High-R pitch motion over three octaves.',{'chaos_r':3.99,'chaos_x':.413,'chaos_burn_in':64,'chaos_octaves':3})],
 'Turing Machine': [('Busy Beaver','Default machine and binary tape.',{}),('Alternator','Alternating-state machine.',{'turing_preset':'Alternator'}),('Marbles pitch','Marbles machine produces pitched material.',{'turing_preset':'Marbles','turing_mode':'Pitch','turing_tape':'01001000'})],
 'Orbital Sequence': [('Eight and five','Union of two orbital cycles.',{}),('Interlock','Complementary interactions of seven and four.',{'orbit_cycle_a':7,'orbit_cycle_b':4,'orbit_mode':'Interlock'}),('Pitch orbit','Pitch motion from two longer orbital cycles.',{'orbit_cycle_a':12,'orbit_cycle_b':7,'orbit_output':'Pitch'})],
 'Geometry Collision': [('Two in a box','Two moving particles inside a box.',{}),('Triangle rhythm','Three particles in triangular geometry.',{'geometry_shape':'Triangle','geometry_particles':3,'geometry_speed':1.3}),('Circular melody','Circular collision geometry converted to pitches.',{'geometry_shape':'Circle','geometry_mode':'Pitch','geometry_particles':2,'geometry_speed':.7})],
}

BLOCKS = {
 'BASS': [('Root pulse','Short root-focused pulses; follows existing harmony.','Pattern',{'pattern':'1,0,0,0','role_root_bias':.85,'gate':.7,'harmonic_strength':1.}),('Walking bass','Close scale movement with drum anchoring.','Scale Walker',{'scale_step':1,'scale_octaves':1,'gate':.85,'groove_follow':.7}),('Broken bass','Displaced rhythmic bass with short gates.','Euclidean',{'pulses':5,'euclidean_rotation':2,'gate':.45,'role_root_bias':.6})],
 'MELODY': [('Close phrase','Small Markov intervals and breathing space.','Markov',{'markov_jump':2,'markov_rest':.15,'markov_stay':.2,'role_width':24}),('Rising sequence','Upward scale bias over a wider register.','Scale Walker',{'scale_direction':.8,'scale_octaves':2,'gate':.65}),('Arpeggio line','Two-octave up/down arpeggio.','Arpeggiator',{'arp_direction':'Up/Down','arp_octaves':2,'arp_pattern':'0,2,4','gate':.6})],
 'CHORD': [('Short stabs','Sparse harmonic attacks with compact voicing.','Euclidean',{'pulses':3,'gate':.4,'harmony_size':3,'harmony_spread':7}),('Strummed chords','Quarter-note chords with ascending strum.','Pattern',{'pattern':'1,0,0,0','harmony_size':4,'gate':1.,'strum_probability':1.,'strum_spacing':.035,'strum_direction':'up'}),('Open voicing','Slower harmonic attacks and wider spread.','Pattern',{'pattern':'1,0,0,0,0,0,0,0','harmony_size':4,'harmony_spread':18,'gate':1.3})],
 'PAD': [('Sustained','Sparse onsets and longer harmonic notes.','Pattern',{'pattern':'1,0,0,0,0,0,0,0','gate':1.5,'role_duration':2.,'pad_sustain':2.,'harmony_size':4}),('Soft strum','Broad, humanized chord spread.','Pattern',{'pattern':'1,0,0,0,0,0,0,0','strum_probability':1.,'strum_spacing':.1,'strum_humanize':.2,'gate':1.5,'pad_sustain':2.}),('Pulsing texture','A soft rhythmic chord bed.','Euclidean',{'pulses':5,'gate':1.2,'velocity_base':.5,'harmony_size':3})],
}


def _record(name, description, kind, algorithm, parameters, identity):
    return {'format':FORMAT,'version':VERSION,'id':'factory:'+identity,'name':name,'description':description,
            'kind':kind,'algorithm':algorithm,'parameters':parameters}


def _sound(block):
    return dict(block_type=block.block_type, target='voice' if getattr(block,'is_drum_voice',False) else 'block',
                mode=block.mode, mutators=[asdict(m) for m in block.mutators], processes=[], midi_expression={}, voices=[])


@lru_cache(maxsize=1)
def _catalog():
    result=[]
    assert set(ALGORITHMS) == set(GENERATORS), 'Every generator needs factory presets'
    for algorithm, variants in ALGORITHMS.items():
        for i,(name,description,parameters) in enumerate(variants):
            result.append(validate(_record(name,description,'algorithm',algorithm,
                {**algorithm_defaults(algorithm),**parameters},f'algorithm/{algorithm}/{i}')))
    for role, variants in BLOCKS.items():
        for i,(name,description,algorithm,parameters) in enumerate(variants):
            block=Block(1,role,role,algorithm,parameters={**ROLE_PROFILES[role],**algorithm_defaults(algorithm),**parameters})
            # Profile metadata is not a runtime parameter.
            for key in ('label','register_min','register_max','register_anchor','root_bias'): block.parameters.pop(key,None)
            raw=_record(name,description,'block',algorithm,block.parameters,f'block/{role}/{i}')
            raw.update(_sound(block)); result.append(validate(raw))
    for i,(name,description,parameters) in enumerate((
        ('Straight kit','Coordinated six-voice kit, preserving your MIDI note map.',{'kit_coordinated':True,'kit_style':'straight','kit_complexity':.2,'kit_syncopation':.1}),
        ('Broken kit','More displaced activity and phrase variation.',{'kit_coordinated':True,'kit_style':'broken','kit_complexity':.6,'kit_syncopation':.5,'kit_variation':.45}),
        ('Metric kit','Metric importance and independent syncopation control.',{'kit_coordinated':True,'kit_engine':'metric','kit_syncopation':.35}),
    )):
        block=Block(1,'Kit','DRUM',parameters=parameters)
        raw=_record(name,description,'block',block.algorithm,parameters,f'block/DRUM/{i}'); raw.update(_sound(block))
        for voice in make_default_drum_voices(block):
            child=_record('Voice','','block',voice.algorithm,{**algorithm_defaults(voice.algorithm),**voice.parameters},'voice')
            child.update(_sound(voice));raw['voices'].append(child)
        result.append(validate(raw))
    for i,(name,description,algorithm,parameters) in enumerate((
        ('Sparse hits','Three distributed hits.','Euclidean',{'pulses':3}),
        ('Rolling hits','Six hits with occasional three-note ratchets.','Euclidean',{'pulses':6,'drum_ratchet_probability':.25,'drum_ratchet_count':3}),
        ('Flam accents','Backbeat-style source pattern with occasional flams.','Pattern',{'pattern':'0,0,0,0,1,0,0,0','drum_flam_probability':.35}),
    )):
        raw=_record(name,description,'block',algorithm,{**algorithm_defaults(algorithm),**parameters},f'voice/{i}')
        raw.update(block_type='DRUM',target='voice',mode='SEQ',mutators=[],processes=[],midi_expression={},voices=[])
        result.append(validate(raw))
    return tuple(result)


def factory_presets(): return deepcopy(_catalog())
