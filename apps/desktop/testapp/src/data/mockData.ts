import { SopDocument, PidSchematic, SandboxScript, NetworkTrace, EnclaveNode, ReviewDeliverable } from '../types';

export const INITIAL_NODES: EnclaveNode[] = [
  {
    id: 'node-01',
    hostname: 'AirBench-Node-01.enclave.local',
    status: 'READY',
    host: '127.0.0.1:8000',
    latency: '0.4 ms',
    policy: 'Strict Mutual Verification',
    fingerprint: 'SHA256:7b:94:a3:21:8c:fe:10:99:a4:23:0d:51:7e:9f:3b:01:88:42:ee:aa:30:19',
    certificateIssuer: 'CN=AirBench Root CA, O=Sovereign Defense Industrial Enclave',
    expires: '2028-12-31'
  },
  {
    id: 'node-02',
    hostname: 'AirBench-Node-02.corp-vpc.internal',
    status: 'STANDBY',
    host: '10.142.0.4:8443',
    latency: '3.8 ms',
    policy: 'TLS 1.3 Pinning / Level 4 Qualified',
    fingerprint: 'SHA256:4d:11:89:f2:c0:3a:77:88:99:12:e3:10:ab:44:cc:dd:55:66:77:88:99:00',
    certificateIssuer: 'CN=Corp Internal Trust CA, OU=Industrial Ops',
    expires: '2027-06-30'
  }
];

export const INITIAL_DOCUMENTS: SopDocument[] = [
  {
    id: 'doc-1',
    code: 'SOP-MNT-022',
    title: 'Unit 4 maintenance review procedure',
    rev: 'Rev 7',
    pages: 26,
    category: 'Maintenance',
    status: 'Indexed',
    passagesCount: 194,
    lastUpdated: '2026-08-14',
    sections: [
      {
        heading: '1.0 Scope and Permitting Bounds',
        text: 'This Standard Operating Procedure governs all scheduled mechanical teardowns, seal replacements, and preventive torque inspections on Unit 4 preheat exchangers and crude boost pumps. Hot work permits must be cosigned by the Area Lead before line depressurization.'
      },
      {
        heading: '2.4 Line Breaking and Blinding Sequence',
        text: 'Positive mechanical isolation requires spectacle blind insertion immediately downstream of suction valve V-102. Bleed valves BV-101 and BV-102 must be opened and tagged to verify zero hydrostatic head before flange unbolting.'
      },
      {
        heading: '3.1 Re-torquing and Gasket Specifications',
        text: 'All Class 300 RF flanges must receive fresh spiral-wound 316SS gaskets with flexible graphite filler. Torquing sequence must follow standard star pattern in three progressive passes: 30%, 70%, and 100% nominal bolt torque (280 N·m for 7/8" B7 studs).'
      }
    ]
  },
  {
    id: 'doc-2',
    code: 'SOP-QAL-017',
    title: 'Deviation and findings management',
    rev: 'Rev 8',
    pages: 16,
    category: 'Quality',
    status: 'Indexed',
    passagesCount: 118,
    lastUpdated: '2026-07-22',
    sections: [
      {
        heading: '1.1 Incident Classification Matrix',
        text: 'Deviations are triaged as Minor (Type I), Moderate (Type II), or Critical (Type III). Critical deviations trigger immediate autonomous enclave freeze and notification to the chief operations engineer within 15 minutes.'
      },
      {
        heading: '2.0 Root Cause Analysis Protocol',
        text: 'Fishbone analysis and 5-Why methodology must be appended to all Type II and Type III discrepancy reports. Containment actions must be logged in the immutable audit ledger.'
      }
    ]
  },
  {
    id: 'doc-3',
    code: 'SOP-SAF-003',
    title: 'Line breaking and positive isolation',
    rev: 'Rev 5',
    pages: 12,
    category: 'Safety',
    status: 'Indexed',
    passagesCount: 92,
    lastUpdated: '2026-09-02',
    sections: [
      {
        heading: '1.0 Fundamental Safety Directives',
        text: 'No pipe spool or pressurized manifold containing hydrocarbons or hazardous chemicals may be opened without verified Double Block and Bleed (DBB) or slip blind isolation.'
      },
      {
        heading: '2.3 Pressure Depressurization and Drain Monitoring',
        text: 'Continuous zero-pressure indication on analog gauge PI-044 is mandatory prior to initiating initial bolt loosening.'
      }
    ]
  },
  {
    id: 'doc-4',
    code: 'SOP-PRC-014',
    title: 'Pump changeover and isolation',
    rev: 'Rev 4',
    pages: 18,
    category: 'Process',
    status: 'Indexed',
    passagesCount: 146,
    lastUpdated: '2026-08-01',
    sections: [
      {
        heading: '1.2 Continuous Feed Stabilization',
        text: 'During pump swap from P-101A to standby unit P-101B, both discharge control valves must ramp proportionally over a 120-second envelope to suppress pressure hammer pulses exceeding 4.5 bar gauge.'
      }
    ]
  },
  {
    id: 'doc-5',
    code: 'SOP-INS-031',
    title: 'Relief valve inspection intervals',
    rev: 'Rev 6',
    pages: 21,
    category: 'Inspection',
    status: 'Indexed',
    passagesCount: 168,
    lastUpdated: '2026-06-19',
    sections: [
      {
        heading: '2.1 Bench Testing and Recertification Cycles',
        text: 'Pressure relief valves exposed to corrosive sour crude streams must undergo ultrasonic wall thickness verification and pop-pressure bench calibration every 24 operating months.'
      }
    ]
  },
  {
    id: 'doc-6',
    code: 'STD-PID-001',
    title: 'P&ID drafting and symbol standard',
    rev: 'Rev 9',
    pages: 44,
    category: 'Engineering',
    status: 'Indexed',
    passagesCount: 312,
    lastUpdated: '2026-09-18',
    sections: [
      {
        heading: '3.0 ISA-5.1 Instrumentation Symbology',
        text: 'Instrument bubbles represent discrete elements. Solid horizontal line denotes primary location accessible to operator; broken line denotes auxiliary back-of-panel installation.'
      }
    ]
  },
  {
    id: 'doc-7',
    code: 'SOP-OPS-009',
    title: 'Crude feed rate adjustment',
    rev: 'Rev 2',
    pages: 9,
    category: 'Operations',
    status: 'Indexed',
    passagesCount: 84,
    lastUpdated: '2026-08-30',
    sections: [
      {
        heading: '1.4 Furnace Preheat Ramp-Up Envelope',
        text: 'Crude feed ramp rates must not exceed 25 m³/hr per 30-minute interval to prevent thermal shock in convection tubes.'
      }
    ]
  },
  {
    id: 'doc-8',
    code: 'SOP-ENV-005',
    title: 'Flare gas recovery monitoring',
    rev: 'Rev 3',
    pages: 14,
    category: 'Environmental',
    status: 'Indexed',
    passagesCount: 122,
    lastUpdated: '2026-05-11',
    sections: [
      {
        heading: '2.0 Compressor Header Pressure Thresholds',
        text: 'Flare gas liquid ring compressors must maintain header vacuum between -25 mm H2O and -5 mm H2O to ensure zero atmospheric discharge to flare tip.'
      }
    ]
  }
];

export const INITIAL_SCHEMATICS: PidSchematic[] = [
  {
    id: 'pid-101',
    title: 'Crude feed and preheat train',
    dwg: '4401-CR-101',
    rev: 'REV C',
    sheet: 'SHEET 01 / 04',
    symbolsCount: 142,
    status: 'Topology mapped',
    statusTone: 'emerald',
    exportState: 'Export ready',
    category: 'Crude Unit',
    symbols: [
      { id: 'sym-1', tag: 'P-101A', type: 'Centrifugal Pump', description: 'Crude Booster Pump A (Electric Drive)', coordinates: 'X: 142, Y: 290', specs: 'Q=180 m³/h, Head=62 m, 75 kW' },
      { id: 'sym-2', tag: 'E-101A', type: 'Shell & Tube Exchanger', description: 'Preheat Train Stage 1 Exchanger', coordinates: 'X: 380, Y: 290', specs: 'Area=420 m², Duty=3.8 MW, Shell: Resids' },
      { id: 'sym-3', tag: 'FCV-104', type: 'Pneumatic Globe Valve', description: 'Crude Feed Rate Flow Control Valve', coordinates: 'X: 520, Y: 240', specs: '6" ANSI 300, Fail-Open (FO), 4-20mA' },
      { id: 'sym-4', tag: 'PI-101', type: 'Pressure Transmitter', description: 'Pump Discharge Pressure Transmitter', coordinates: 'X: 180, Y: 210', specs: 'Range: 0-16 bar, HART Protocol' },
      { id: 'sym-5', tag: 'TI-104', type: 'Temperature Element', description: 'Preheat Exchanger Outlet Thermowell', coordinates: 'X: 430, Y: 210', specs: 'Pt100 RTD, Class A, Range: 20-350°C' }
    ],
    connections: [
      { from: 'P-101A', to: 'E-101A', lineTag: '8"-CR-10101-A1', spec: 'Carbon Steel A106 Gr.B' },
      { from: 'E-101A', to: 'FCV-104', lineTag: '8"-CR-10102-A1', spec: 'Carbon Steel A106 Gr.B' },
      { from: 'FCV-104', to: 'C-101 (Battery Limit)', lineTag: '8"-CR-10103-A1', spec: 'Carbon Steel A106 Gr.B' }
    ]
  },
  {
    id: 'pid-102',
    title: 'Atmospheric column overhead',
    dwg: '4401-CR-102',
    rev: 'REV B',
    sheet: 'SHEET 02 / 04',
    symbolsCount: 98,
    status: 'Reconstruction sync',
    statusTone: 'amber',
    exportState: 'In review',
    category: 'Distillation',
    symbols: [
      { id: 'sym-10', tag: 'C-101', type: 'Fractionation Column', description: 'Main Atmospheric Distillation Tower', coordinates: 'X: 120, Y: 180', specs: 'Dia=4.2 m, H=48 m, 42 Sieve Trays' },
      { id: 'sym-11', tag: 'E-102', type: 'Air-Cooled Condenser', description: 'Overhead Fin-Fan Condenser Bank', coordinates: 'X: 380, Y: 140', specs: '8 Bays, Duty=14.2 MW, 316L Bundles' },
      { id: 'sym-12', tag: 'V-104', type: 'Horizontal Accumulator', description: 'Overhead Naphtha & Reflux Drum', coordinates: 'X: 410, Y: 320', specs: 'Vol=28 m³, Design P=5.5 bar, Boot separator' },
      { id: 'sym-13', tag: 'TI-108', type: 'Temperature Indicator', description: 'Overhead Vapor Column Top Temperature', coordinates: 'X: 180, Y: 160', specs: '0-250°C, Dual thermocouple' }
    ],
    connections: [
      { from: 'C-101', to: 'E-102', lineTag: '24"-OV-10201-B2', spec: 'Low Carbon Alloy Steel' },
      { from: 'E-102', to: 'V-104', lineTag: '16"-OV-10202-B2', spec: 'Low Carbon Alloy Steel' }
    ]
  }
];

export const INITIAL_SANDBOX_FILES: SandboxScript[] = [
  {
    id: 'pressure_drop',
    name: 'pressure_drop.py',
    type: 'Python',
    timestamp: '10:23 AM',
    size: '4.2 KB',
    description: 'Colebrook-White hydraulic gradient calc',
    code: `# Darcy-Weisbach pressure drop · P-101 discharge line
# Fluid: High-viscosity process slurry @ 45°C
import math

Q = 0.025 # Volumetric flow rate (m³/s)
D = 0.1016 # Internal pipe diameter (m) [4-inch SCH 40]
L = 47.5 # Total equivalent length (m)
rho = 850 # Fluid density (kg/m³)
mu = 0.004 # Dynamic viscosity (Pa·s)
eps = 4.6e-5 # Commercial steel roughness (m)

# Hydraulic kinematics
A = math.pi * (D / 2) ** 2
v = Q / A
Re = rho * v * D / mu

# Colebrook-White friction factor (iterative convergence)
f = 0.02
for _ in range(100):
    f_new = (1 / (-2 * math.log10(eps / (3.7 * D) + 2.51 / (Re * f**0.5)))) ** 2
    if abs(f_new - f) < 1e-10:
        break
    f = f_new

dp_kpa = (f * (L / D) * (rho * v**2 / 2)) / 1000
print(f"Velocity: {v:.3f} m/s | Re: {Re:,.1f} | f: {f:.5f} | ΔP: {dp_kpa:.2f} kPa")
`,
    expectedOutput: `[$] python3.11 isolated_runtime/pressure_drop.py --enclave=strict
[+] Hydraulic simulation converged successfully (3 iterations)
| Velocity: 3.084 m/s | Re: 66,547.2 | f: 0.02114 | ΔP: 398.24 kPa
Process finished with exit code 0. Zero telemetry packets sent outside local perimeter.`,
    variables: {
      Q: 0.025,
      D: 0.1016,
      L: 47.5,
      rho: 850,
      mu: 0.004,
      eps: 0.000046
    }
  },
  {
    id: 'findings_parser',
    name: 'findings_parser.py',
    type: 'Python',
    timestamp: 'Yesterday',
    size: '12.8 KB',
    description: 'Extract P&ID node telemetry from sensor CSV logs',
    code: `# P&ID Node Telemetry Extractor & Anomaly Parser
import json

telemetry_nodes = [
    {"node": "P-101A", "bearing_temp_c": 64.2, "vibration_mms": 1.84, "status": "NOMINAL"},
    {"node": "E-101A", "inlet_p_kpa": 842.1, "outlet_p_kpa": 443.9, "status": "NOMINAL"},
    {"node": "FCV-104", "cv_percent": 68.4, "stem_travel_err": 0.02, "status": "NOMINAL"},
    {"node": "C-101", "tray12_temp_c": 184.6, "delta_p_mbar": 42.1, "status": "NOMINAL"}
]

print("[+] Parsed 4 sensor telemetric records from local shared memory block")
for node in telemetry_nodes:
    print(f" -> {node['node']:<8} Status: {node['status']:<8} Metrics: {list(node.items())[1:3]}")

print("[✓] Anomaly verification complete: 0 threshold breaches detected across active loops.")
`,
    expectedOutput: `[$] python3.11 isolated_runtime/findings_parser.py --enclave=strict
[+] Parsed 4 sensor telemetric records from local shared memory block
 -> P-101A    Status: NOMINAL  Metrics: [('bearing_temp_c', 64.2), ('vibration_mms', 1.84)]
 -> E-101A    Status: NOMINAL  Metrics: [('inlet_p_kpa', 842.1), ('outlet_p_kpa', 443.9)]
 -> FCV-104   Status: NOMINAL  Metrics: [('cv_percent', 68.4), ('stem_travel_err', 0.02)]
 -> C-101     Status: NOMINAL  Metrics: [('tray12_temp_c', 184.6), ('delta_p_mbar', 42.1)]
[✓] Anomaly verification complete: 0 threshold breaches detected across active loops.
Process finished with exit code 0. Zero telemetry egress.`,
    variables: {}
  },
  {
    id: 'thermal_loop',
    name: 'thermal_loop.py',
    type: 'Python',
    timestamp: 'Sep 28',
    size: '8.1 KB',
    description: 'Heat exchanger effectiveness & LMTD routine',
    code: `# Shell and Tube Heat Exchanger LMTD & UA Solver
import math

T_hot_in = 240.0   # °C
T_hot_out = 160.0  # °C
T_cold_in = 35.0   # °C
T_cold_out = 95.0  # °C
Q_kw = 3800.0      # Heat duty in kW

delta_T1 = T_hot_in - T_cold_out
delta_T2 = T_hot_out - T_cold_in
LMTD = (delta_T1 - delta_T2) / math.log(delta_T1 / delta_T2)

F_correction = 0.92  # 1-2 shell pass correction factor
UA = (Q_kw * 1000) / (F_correction * LMTD)

print(f"Counter-current LMTD: {LMTD:.2f} °C")
print(f"Corrected LMTD (F={F_correction}): {F_correction * LMTD:.2f} °C")
print(f"Required overall UA: {UA:,.1f} W/K | Estimated Area (U=450 W/m²K): {UA/450:.1f} m²")
`,
    expectedOutput: `[$] python3.11 isolated_runtime/thermal_loop.py --enclave=strict
Counter-current LMTD: 134.63 °C
Corrected LMTD (F=0.92): 123.86 °C
Required overall UA: 30,679.8 W/K | Estimated Area (U=450 W/m²K): 68.2 m²
Process finished with exit code 0. Execution: 9.8 ms.`,
    variables: {}
  },
  {
    id: 'viscosity_calc',
    name: 'viscosity_calc.py',
    type: 'Python',
    timestamp: 'Sep 25',
    size: '3.4 KB',
    description: 'Andrade equation temperature-dependent viscosity',
    code: `# Andrade Temperature-Dependent Kinematic Viscosity Model
import math

temps_c = [20, 40, 60, 80, 100]
A = 0.000125  # Model coefficient
B = 1420.0    # Activation temperature in Kelvin

print(f"{'Temp (°C)':<12}{'Temp (K)':<12}{'Viscosity (cP)':<15}")
print("-" * 39)
for tc in temps_c:
    tk = tc + 273.15
    mu_cp = A * math.exp(B / tk) * 1000
    print(f"{tc:<12}{tk:<12.2f}{mu_cp:<15.3f}")
`,
    expectedOutput: `[$] python3.11 isolated_runtime/viscosity_calc.py
Temp (°C)   Temp (K)    Viscosity (cP) 
---------------------------------------
20          293.15      15.932         
40          313.15      11.662         
60          333.15      8.831          
80          353.15      6.877          
100         373.15      5.489          
Process finished with exit code 0.`,
    variables: {}
  },
  {
    id: 'navier_stokes_2d',
    name: 'navier_stokes_2d.py',
    type: 'Python',
    timestamp: 'Sep 20',
    size: '26.4 KB',
    description: 'Cavity flow finite difference solver',
    code: `# 2D Incompressible Lid-Driven Cavity Solver (Stream-Vorticity)
nx, ny = 41, 41
nit = 50
dx = 2.0 / (nx - 1)
dy = 2.0 / (ny - 1)
dt = 0.001
Re = 100.0

print(f"[+] Initialized 2D grid {nx}x{ny}, Re={Re}, dt={dt}")
print("[+] Computing Poisson pressure-correction iterations...")
print(f"[✓] Converged at step 42 with L2 residual: 8.42e-7")
print(f"    Center vortex core located at coordinates: (x=0.528, y=0.562)")
`,
    expectedOutput: `[$] python3.11 isolated_runtime/navier_stokes_2d.py --enclave=strict
[+] Initialized 2D grid 41x41, Re=100.0, dt=0.001
[+] Computing Poisson pressure-correction iterations...
[✓] Converged at step 42 with L2 residual: 8.42e-7
    Center vortex core located at coordinates: (x=0.528, y=0.562)
Execution completed in 44.1 ms. Clean memory sandbox exit.`,
    variables: {}
  }
];

export const INITIAL_NETWORK_TRACES: NetworkTrace[] = [
  {
    id: 'trace-1',
    timestamp: '11:24:15',
    route: 'LOCAL',
    endpoint: '127.0.0.1:8000/v1/embeddings',
    method: 'POST',
    status: 200,
    payloadBytes: 4096,
    model: 'nomic-embed-text',
    quantization: 'q4_k_m',
    headers: {
      'Host': '127.0.0.1:8000',
      'Content-Type': 'application/json',
      'X-AirBench-Enclave-Policy': 'Strict-Zero-Egress',
      'X-Node-ID': 'AirBench-Node-01'
    },
    curlCommand: `curl -s -X POST http://127.0.0.1:8000/v1/embeddings \\
  -H "Content-Type: application/json" \\
  -d '{"model": "nomic-embed-text", "input": "Standard Operating Procedure line breaking isolation criteria"}'`
  },
  {
    id: 'trace-2',
    timestamp: '11:24:45',
    route: 'LOCAL',
    endpoint: '127.0.0.1:8000/v1/chat/completions',
    method: 'POST',
    status: 200,
    payloadBytes: 12450,
    model: 'qwen2.5-coder-7b',
    quantization: 'q4_k_m',
    headers: {
      'Host': '127.0.0.1:8000',
      'Content-Type': 'application/json',
      'X-AirBench-Enclave-Policy': 'Strict-Zero-Egress',
      'X-Node-ID': 'AirBench-Node-01'
    },
    curlCommand: `curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model": "qwen2.5-coder-7b", "prompt": "Synthesize P&ID telemetry for Unit 4 crude preheat loop", "max_tokens": 512}'`
  },
  {
    id: 'trace-3',
    timestamp: '11:25:15',
    route: 'LOCAL',
    endpoint: '127.0.0.1:8000/v1/chat/completions',
    method: 'POST',
    status: 200,
    payloadBytes: 56340,
    model: 'deepseek-coder-6.7b',
    quantization: 'q4_k_m',
    headers: {
      'Host': '127.0.0.1:8000',
      'Content-Type': 'application/json',
      'X-AirBench-Enclave-Policy': 'Strict-Zero-Egress',
      'X-Node-ID': 'AirBench-Node-01'
    },
    curlCommand: `curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model": "deepseek-coder-6.7b", "messages": [{"role": "user", "content": "Analyze P&ID loop telemetry and verify compliance"}], "temperature": 0.1}'`
  },
  {
    id: 'trace-4',
    timestamp: '11:26:05',
    route: 'LOCAL',
    endpoint: '127.0.0.1:8000/v1/chat/completions',
    method: 'POST',
    status: 200,
    payloadBytes: 8214,
    model: 'qwen2.5-coder-7b',
    quantization: 'q4_k_m',
    headers: {
      'Host': '127.0.0.1:8000',
      'Content-Type': 'application/json',
      'X-AirBench-Enclave-Policy': 'Strict-Zero-Egress',
      'X-Node-ID': 'AirBench-Node-01'
    },
    curlCommand: `curl -s -X POST http://127.0.0.1:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model": "qwen2.5-coder-7b", "messages": [{"role": "user", "content": "Execute Colebrook-White friction factor verification in sandbox"}], "temperature": 0.1}'`
  }
];

export const INITIAL_DELIVERABLES: ReviewDeliverable[] = [];

export const INITIAL_CONVERSATION_SESSIONS: {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  model: string;
  deliverableType: string;
  lastQuerySnippet: string;
  messages: any[];
}[] = [
  {
    id: 'session-01',
    title: 'Crude Loop 101 Hydraulic Gradient & Colebrook-White Solver',
    createdAt: 'Today, 09:14 AM',
    updatedAt: 'Today, 09:15 AM',
    model: 'qwen2.5-coder-7b',
    deliverableType: 'Spreadsheet (.xlsx)',
    lastQuerySnippet: 'Run Python hydraulic pressure drop simulation with Colebrook-White friction...',
    messages: [
      {
        id: 'msg-s1-1',
        role: 'user',
        timestamp: '09:14 AM',
        text: 'Run Python hydraulic pressure drop simulation with Colebrook-White friction for Crude Loop 101. Provide process telemetry spreadsheet deliverable.',
        route: 'Code Specialist (qwen2.5-coder-7b)',
        attachedFiles: [
          {
            id: 'att-1',
            name: 'hydraulic_gradient_measurements.xlsx',
            size: 48210,
            type: 'excel',
            extension: '.xlsx'
          }
        ]
      },
      {
        id: 'msg-s1-2',
        role: 'assistant',
        timestamp: '09:15 AM',
        text: '### Process Telemetry & Hydraulic Gradient Matrix\n\n| Timestamp | Equipment Tag | Parameter | Measured Value | Design Limit | Variance | Invariant Status |\n|---|---|---|---|---|---|---|\n| 09:14:01 | **P-101A** | Volumetric Flow Rate | 140.0 m³/h | 165.0 m³/h | -15.1% | NOMINAL |\n| 09:14:02 | **P-101A** | Discharge Head | 14.2 bar gauge | 20.0 bar gauge | -29.0% | PASSED |\n| 09:14:03 | **E-101A** | Inlet Temperature | 88.4 °C | 120.0 °C | -26.3% | NOMINAL |\n| 09:14:04 | **E-101A** | Outlet Temperature | 114.6 °C | 145.0 °C | -20.9% | NOMINAL |\n| 09:14:05 | **FCV-104** | Stem Position | 64.2 % | 100.0 % | -35.8% | REGULATING |\n| 09:14:06 | **PI-101** | Line Static Pressure | 11.8 bar gauge | 16.0 bar gauge | -26.2% | VERIFIED |\n\n### Tabular Telemetry Invariant Notes\n1. Friction factor f = 0.0218 computed iteratively via Colebrook-White formula.\n2. Total pipeline head loss ΔP = 48.2 kPa over 85m schedule 40 carbon steel pipe.\n\n[EMIT_REPORT: crude_loop_hydraulic_matrix.xlsx]',
        route: 'qwen2.5-coder-7b',
        deliverable: {
          id: 'del-s1',
          title: 'Crude Loop 101 Hydraulic Matrix',
          type: 'Spreadsheet',
          format: 'xlsx',
          sourceRoute: 'qwen2.5-coder-7b',
          timestamp: '09:15 AM',
          summary: 'Synthesized with zero preamble by qwen2.5-coder-7b for Crude Loop 101 hydraulics.',
          content: '### Process Telemetry & Hydraulic Gradient Matrix\n\n| Timestamp | Equipment Tag | Parameter | Measured Value | Design Limit | Variance | Invariant Status |\n|---|---|---|---|---|---|---|\n| 09:14:01 | **P-101A** | Volumetric Flow Rate | 140.0 m³/h | 165.0 m³/h | -15.1% | NOMINAL |\n| 09:14:02 | **P-101A** | Discharge Head | 14.2 bar gauge | 20.0 bar gauge | -29.0% | PASSED |\n| 09:14:03 | **E-101A** | Inlet Temperature | 88.4 °C | 120.0 °C | -26.3% | NOMINAL |\n| 09:14:04 | **E-101A** | Outlet Temperature | 114.6 °C | 145.0 °C | -20.9% | NOMINAL |\n| 09:14:05 | **FCV-104** | Stem Position | 64.2 % | 100.0 % | -35.8% | REGULATING |\n| 09:14:06 | **PI-101** | Line Static Pressure | 11.8 bar gauge | 16.0 bar gauge | -26.2% | VERIFIED |\n\n[EMIT_REPORT: crude_loop_hydraulic_matrix.xlsx]',
          metadata: {
            tokens: 420,
            rowsCount: 7
          }
        }
      }
    ]
  },
  {
    id: 'session-02',
    title: 'Unit 4 Emergency Depressurization SOP Briefing Deck',
    createdAt: 'Yesterday, 14:22 PM',
    updatedAt: 'Yesterday, 14:23 PM',
    model: 'deepseek-coder-6.7b',
    deliverableType: 'Presentation (.pptx)',
    lastQuerySnippet: 'Prepare executive 4-slide briefing deck on emergency depressurization thresholds...',
    messages: [
      {
        id: 'msg-s2-1',
        role: 'user',
        timestamp: '14:22 PM',
        text: 'Prepare executive 4-slide briefing deck on Unit 4 emergency depressurization thresholds and isolation procedures under SOP-PRC-014.',
        route: 'Static Analysis & Debug (deepseek-coder-6.7b)',
        attachedFiles: [
          {
            id: 'att-2',
            name: 'SOP-PRC-014-Depressurization.pdf',
            size: 198400,
            type: 'pdf',
            extension: '.pdf'
          }
        ]
      },
      {
        id: 'msg-s2-2',
        role: 'assistant',
        timestamp: '14:23 PM',
        text: '### Slide 1: Sovereign Engineering Briefing & Boundary Verification\n- AirBench Sovereign Isolated Hardware Enclave Analysis\n- Target Context: Unit 4 emergency depressurization thresholds\n- Cryptographic Boundary: Hardware Loopback 127.0.0.1:8000 | Zero-Egress\n\n### Slide 2: Process Topology & Loop Instrumentation\n- Emergency blowdown rate rated for 240,000 kg/h to flare stack\n- Primary isolation valves BDV-101 and BDV-102 fail-open to safe position\n- Hydrocarbon inventory depressurized from 18.0 bar to 2.0 bar in under 12 minutes\n\n### Slide 3: Invariant & Safety Compliance Matrix\n| Component | Metric | Enclave Reading | Standard Envelope | Result |\n|---|---|---|---|---|\n| BDV-101 | Actuator Stroke | 3.2 seconds | Max 5.0 seconds | COMPLIANT |\n| Flare Header | Thermal Backpressure | 1.8 bar gauge | Limit 3.5 bar | NOMINAL |\n| Interlock Seal | Cryptographic Key | SHA256-verified | Level 4 Boundary | SECURE |\n\n### Slide 4: Operational Directives & Action Items\n- Quarterly proof-testing of pneumatic solenoid valves required\n- Confirm nitrogen purge blanket active prior to restart sequence\n\n[EMIT_REPORT: unit4_depressurization_briefing.pptx]',
        route: 'deepseek-coder-6.7b',
        deliverable: {
          id: 'del-s2',
          title: 'Unit 4 Depressurization Briefing',
          type: 'Presentation',
          format: 'pptx',
          sourceRoute: 'deepseek-coder-6.7b',
          timestamp: '14:23 PM',
          summary: 'Multi-slide presentation deck covering emergency blowdown and isolation criteria.',
          content: '### Slide 1: Sovereign Engineering Briefing & Boundary Verification\n- AirBench Sovereign Isolated Hardware Enclave Analysis\n- Target Context: Unit 4 emergency depressurization thresholds\n\n### Slide 2: Process Topology & Loop Instrumentation\n- Emergency blowdown rate rated for 240,000 kg/h to flare stack\n- Primary isolation valves BDV-101 and BDV-102 fail-open to safe position\n\n### Slide 3: Invariant & Safety Compliance Matrix\n| Component | Metric | Enclave Reading | Standard Envelope | Result |\n|---|---|---|---|---|\n| BDV-101 | Actuator Stroke | 3.2 seconds | Max 5.0 seconds | COMPLIANT |\n\n### Slide 4: Operational Directives & Action Items\n- Quarterly proof-testing of pneumatic solenoid valves required\n\n[EMIT_REPORT: unit4_depressurization_briefing.pptx]',
          metadata: {
            tokens: 380,
            slidesCount: 4
          }
        }
      }
    ]
  },
  {
    id: 'session-03',
    title: 'Crude Booster P-101A Double Block & Bleed Safety Memorandum',
    createdAt: 'Oct 2, 11:05 AM',
    updatedAt: 'Oct 2, 11:07 AM',
    model: 'deepseek-coder-6.7b',
    deliverableType: 'Word Document (.docx)',
    lastQuerySnippet: 'Draft formal engineering investigation memorandum on isolation criteria for P-101A...',
    messages: [
      {
        id: 'msg-s3-1',
        role: 'user',
        timestamp: '11:05 AM',
        text: 'Draft compliance verification memo for Unit 4 isolation procedure and Double Block & Bleed manifold on booster pump P-101A.',
        route: 'Static Analysis & Debug (deepseek-coder-6.7b)',
        attachedFiles: [
          {
            id: 'att-3',
            name: 'DWG-4401-CR-101.docx',
            size: 312000,
            type: 'doc',
            extension: '.docx'
          }
        ]
      },
      {
        id: 'msg-s3-2',
        role: 'assistant',
        timestamp: '11:07 AM',
        text: '### Engineering Investigation Memorandum: Process Loop Integrity\nSubject: **Automated Synthesis and Verification of Unit Operating Parameters**\nClassification: **Enclave Confidential | Sovereign Local Execution**\n\n### 1. Scope & Objective\nThis technical memorandum reviews the topological parameters, pressure bounds, and sensor calibrations specified in query.\n\n### 2. Engineering Verification Matrix\n| Inspection Tag | Specification Metric | Calculated Value | Operational Limit | Compliance Status |\n|---|---|---|---|---|\n| Loop 101 | Operating Pressure | 14.2 bar gauge | 20.0 bar gauge | NOMINAL |\n| Line 101-CR-8\" | Fluid Velocity | 2.12 m/s | 3.50 m/s | ACCEPTABLE |\n| FCV-104 | Actuator Response | 64.2% Open | Fail-Open | VERIFIED |\n| DBB Boundary | Leakage Rate | 0.00 mL/min | 0.00 mL/min | SEALED |\n\n### 3. Technical Observations\n1. **Hydraulic Dynamics**: Fluid velocity of 2.12 m/s resides well below erosion thresholds.\n2. **Double Block & Bleed**: Isolation manifold complies with safety procedure SOP-MNT-022.\n3. **Hardware Security**: All mathematical operations executed inside the sovereign boundary without external API dependencies.\n\n[EMIT_REPORT: p101a_safety_memorandum.docx]',
        route: 'deepseek-coder-6.7b',
        deliverable: {
          id: 'del-s3',
          title: 'P-101A Safety Memorandum',
          type: 'Document',
          format: 'docx',
          sourceRoute: 'deepseek-coder-6.7b',
          timestamp: '11:07 AM',
          summary: 'Technical investigation dossier covering DBB isolation and operating parameters.',
          content: '### Engineering Investigation Memorandum: Process Loop Integrity\nSubject: **Automated Synthesis and Verification of Unit Operating Parameters**\nClassification: **Enclave Confidential | Sovereign Local Execution**\n\n### 1. Scope & Objective\nThis technical memorandum reviews the topological parameters, pressure bounds, and sensor calibrations.\n\n### 2. Engineering Verification Matrix\n| Inspection Tag | Specification Metric | Calculated Value | Operational Limit | Compliance Status |\n|---|---|---|---|---|\n| Loop 101 | Operating Pressure | 14.2 bar gauge | 20.0 bar gauge | NOMINAL |\n| Line 101-CR-8\" | Fluid Velocity | 2.12 m/s | 3.50 m/s | ACCEPTABLE |\n| FCV-104 | Actuator Response | 64.2% Open | Fail-Open | VERIFIED |\n| DBB Boundary | Leakage Rate | 0.00 mL/min | 0.00 mL/min | SEALED |\n\n[EMIT_REPORT: p101a_safety_memorandum.docx]',
          metadata: {
            tokens: 360,
            wordCount: 185
          }
        }
      }
    ]
  }
];

