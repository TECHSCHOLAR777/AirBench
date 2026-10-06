export interface PidCorpusDrawing {
  id: string;
  tag: string;
  title: string;
  unit: string;
  thumb: string;
  display: string;
  width: number;
  height: number;
  node_count: number;
  edge_count: number;
  labels: {
    crossing: number;
    general: number;
    connector: number;
    instrumentation: number;
    valve: number;
    arrow: number;
    background: number;
  };
  dwgNumber: string;
  revision: string;
  sheet: string;
  description: string;
  keyEquipment: {
    tag: string;
    type: string;
    description: string;
    specs: string;
    x: number;
    y: number;
  }[];
  qaKnowledge: {
    sampleQuestions: string[];
    summary: string;
    operatingEnvelope: string;
    isolationPoints: string[];
  };
}

export const PID_CORPUS_DRAWINGS: PidCorpusDrawing[] = [
  {
    id: "0",
    tag: "PID-101",
    title: "Crude feed and preheat train",
    unit: "Unit 100 - Crude distillation",
    thumb: "/pid-corpus/0-thumb.jpg",
    display: "/pid-corpus/0-display.jpg",
    width: 7168,
    height: 4562,
    node_count: 452,
    edge_count: 496,
    dwgNumber: "DWG: 4401-CR-101",
    revision: "REV C",
    sheet: "SHEET 01 / 04",
    description: "Atmospheric crude desalter feed pumps P-101A/B through multi-pass heat exchanger train E-101A-D to preheat convection furnace.",
    labels: {
      crossing: 92,
      general: 34,
      connector: 235,
      instrumentation: 25,
      arrow: 4,
      valve: 58,
      background: 4
    },
    keyEquipment: [
      { tag: "P-101A", type: "Centrifugal Pump", description: "Crude Booster Pump A (Electric Drive, 75 kW)", specs: "Q=180 m³/h, Head=62 m, API 610 OH2", x: 1608, y: 1478 },
      { tag: "P-101B", type: "Centrifugal Pump", description: "Crude Booster Pump B (Standby Steam Turbine)", specs: "Q=180 m³/h, Head=62 m, 3600 rpm", x: 1859, y: 1478 },
      { tag: "E-101A", type: "Shell & Tube Exchanger", description: "Preheat Train Stage 1 Exchanger", specs: "Area=420 m², Duty=3.8 MW, Design P=16 bar", x: 3114, y: 2481 },
      { tag: "FCV-104", type: "Flow Control Valve", description: "Crude Feed Rate Globe Control Valve", specs: "6\" ANSI 300, Air-to-Open (FO), 4-20mA HART", x: 4117, y: 2481 },
      { tag: "PI-101", type: "Pressure Transmitter", description: "Pump P-101A Discharge Pressure Indicator", specs: "Range: 0-25 bar, Dual diaphragm seal", x: 1107, y: 976 },
      { tag: "TI-104", type: "Temperature Transmitter", description: "Preheat Exchanger E-101A Outlet Thermowell", specs: "Pt100 RTD Class A, 0-350°C", x: 3615, y: 2481 },
      { tag: "PSV-101", type: "Safety Relief Valve", description: "Exchanger Shell Thermal Expansion Relief", specs: "Set Pressure: 18.5 bar gauge, 2\"x3\" flanged", x: 4619, y: 2230 }
    ],
    qaKnowledge: {
      sampleQuestions: [
        "What is the designated fail position for control valve FCV-104?",
        "Identify the primary isolation valves surrounding pump P-101A.",
        "What are the design pressure and temperature limits for line 8\"-CR-10101-A1?",
        "List all temperature and pressure instrumentation on the E-101A preheat loop."
      ],
      summary: "This drawing depicts the primary desalted crude booster loop. Fluid is pressurized from the desalter boot at 4.2 bar gauge to 14.8 bar gauge by centrifugal pump P-101A, routing through shell-and-tube preheat exchanger E-101A to maximize energy recovery from atmospheric column bottoms resid.",
      operatingEnvelope: "Normal Operating Pressure: 12.8 bar gauge | Design Pressure: 18.5 bar gauge | Operating Temperature: 148.2 °C | Fluid: Heavy Sour Crude (API 29.4°)",
      isolationPoints: [
        "Suction Block Valve: AV-22130 (Manual wedge gate, Locked Open)",
        "Discharge Check Valve: WX-78817 (Swing check with external counterweight)",
        "Discharge Double Block & Bleed: AV-70118 and BV-101 drain bleed",
        "Control Valve Bypass: 3-valve manifold around FCV-104 with manual globe bypass"
      ]
    }
  },
  {
    id: "1",
    tag: "PID-102",
    title: "Atmospheric column overhead",
    unit: "Unit 100 - Crude distillation",
    thumb: "/pid-corpus/1-thumb.jpg",
    display: "/pid-corpus/1-display.jpg",
    width: 7168,
    height: 4562,
    node_count: 450,
    edge_count: 500,
    dwgNumber: "DWG: 4401-CR-102",
    revision: "REV B",
    sheet: "SHEET 02 / 04",
    description: "Atmospheric tower C-101 top vapor line, overhead air-cooled fin-fan condenser banks E-102, and reflux drum accumulator V-104.",
    labels: {
      crossing: 105,
      general: 36,
      connector: 226,
      valve: 56,
      instrumentation: 19,
      arrow: 4,
      background: 4
    },
    keyEquipment: [
      { tag: "C-101", type: "Distillation Column", description: "Atmospheric Crude Fractionator Column", specs: "Dia=4.2 m, H=48 m, 42 Sieve Trays", x: 1200, y: 1400 },
      { tag: "E-102", type: "Fin-Fan Condenser", description: "Overhead Vapor Air-Cooled Exchanger Bank", specs: "8 Bays, Duty=14.2 MW, 316L Stainless Tubes", x: 3400, y: 1100 },
      { tag: "V-104", type: "Horizontal Accumulator", description: "Naphtha Overhead Reflux & Water Boot Drum", specs: "Vol=28 m³, Operating P=1.85 bar gauge", x: 4200, y: 2600 },
      { tag: "P-104A", type: "Reflux Pump", description: "Top Tray Reflux Return Pump", specs: "Q=110 m³/h, Head=54 m", x: 4600, y: 3400 },
      { tag: "TCV-102", type: "Temperature Control Valve", description: "Overhead Column Top Temperature Controller", specs: "8\" Globe Valve, Fail-Close", x: 3800, y: 1800 }
    ],
    qaKnowledge: {
      sampleQuestions: [
        "How is column top temperature controlled during varying ambient temperature?",
        "Where does the boot water drain from reflux drum V-104 discharge?",
        "What are the interlocks on reflux pump P-104A trip?",
        "Explain the piping spec transition from column vapor line to condenser E-102."
      ],
      summary: "Captures the top fractionation stage of crude oil. Hydrocarbon vapor at 142.5 °C exits column top via 24\"-OV line, condenses across fin-fan cooler E-102, and separates into unstabilized naphtha distillate, reflux return, and sour water condensate inside 3-phase drum V-104.",
      operatingEnvelope: "Vapor Influx: 42,500 kg/h | Top Tray Temp: 142.5 °C | Overhead Pressure: 1.85 bar gauge | Reflux Ratio (R/D): 2.45",
      isolationPoints: [
        "Overhead Vapor Isolation: Full-bore spectacle blind at C-101 nozzle N1",
        "Reflux Line DBB: Dual block valves with telltale bleed BV-108",
        "Sour water boot automatic drain shutoff on low interface level (LIC-104)"
      ]
    }
  },
  {
    id: "2",
    tag: "PID-103",
    title: "Debutanizer reflux loop",
    unit: "Unit 200 - Light ends recovery",
    thumb: "/pid-corpus/2-thumb.jpg",
    display: "/pid-corpus/2-display.jpg",
    width: 7168,
    height: 4562,
    node_count: 434,
    edge_count: 477,
    dwgNumber: "DWG: 4402-LE-201",
    revision: "REV D",
    sheet: "SHEET 01 / 02",
    description: "Light ends debutanizer fractionator overhead, total condenser, and LPG reflux splitter loop.",
    labels: {
      crossing: 100,
      general: 32,
      connector: 216,
      instrumentation: 28,
      valve: 53,
      arrow: 1,
      background: 4
    },
    keyEquipment: [
      { tag: "C-201", type: "Debutanizer Tower", description: "Light Ends Debutanizer Column (30 Valve Trays)", specs: "Dia=2.4 m, Design P=15.0 bar gauge", x: 1400, y: 1600 },
      { tag: "E-201", type: "Water-Cooled Condenser", description: "Shell-and-Tube LPG Overhead Condenser", specs: "Duty=6.4 MW, Cooling water in tubes", x: 3100, y: 1200 },
      { tag: "V-201", type: "Debutanizer Reflux Drum", description: "Overhead LPG Accumulator", specs: "Design P=16 bar, CS A516 Gr.70", x: 4400, y: 2200 },
      { tag: "PCV-201", type: "Backpressure Control Valve", description: "Hot-Gas Vapor Bypass Split-Range Valve", specs: "4\" ANSI 300 Equal Percentage", x: 3600, y: 950 }
    ],
    qaKnowledge: {
      sampleQuestions: [
        "What prevents LPG condensation in the hot gas bypass line?",
        "What is the relief setpoint on the debutanizer reflux drum PSV-201?",
        "Trace the path from C-201 reboiler return to debutanizer bottoms."
      ],
      summary: "Governs recovery of C3/C4 liquefied petroleum gas. Tower overhead vapor is condensed and split between reflux return to hold Reid Vapor Pressure (RVP) on debutanizer bottoms gasoline.",
      operatingEnvelope: "Tower Top Pressure: 11.2 bar gauge | Top Temp: 68.0 °C | Bottom Temp: 175.0 °C",
      isolationPoints: [
        "Relief valve PSV-201 dual car-sealed open block valves with interlock key",
        "Reflux pump suction strainer blowdown valve with threaded cap"
      ]
    }
  },
  {
    id: "3",
    tag: "PID-104",
    title: "Hydrotreater reactor loop",
    unit: "Unit 300 - Distillate hydrotreating",
    thumb: "/pid-corpus/3-thumb.jpg",
    display: "/pid-corpus/3-display.jpg",
    width: 7168,
    height: 4562,
    node_count: 629,
    edge_count: 688,
    dwgNumber: "DWG: 4403-HT-301",
    revision: "REV E",
    sheet: "SHEET 01 / 05",
    description: "High pressure hydrogen recycle gas compressor loop, combined feed furnace, and fixed bed hydrotreating catalytic reactor R-301.",
    labels: {
      crossing: 116,
      general: 42,
      connector: 337,
      valve: 88,
      instrumentation: 40,
      arrow: 2,
      background: 4
    },
    keyEquipment: [
      { tag: "R-301", type: "Fixed Bed Reactor", description: "Diesel Hydrodesulfurization Reactor (NiMo Cat)", specs: "Operating P=65 bar, Design T=420°C, 2.25Cr-1Mo-V", x: 2800, y: 1800 },
      { tag: "K-301", type: "Recycle Gas Compressor", description: "Centrifugal Hydrogen Recycle Compressor", specs: "Shaft Power=1.8 MW, Dry gas mechanical seals", x: 1200, y: 2800 },
      { tag: "H-301", type: "Fired Heater", description: "Combined Feed Hydrotreater Furnace", specs: "Heat Absorption=8.5 MW, Low-NOx burners", x: 2100, y: 1500 },
      { tag: "V-301", type: "High Pressure Separator", description: "Cold High Pressure Hydrotreater Drum", specs: "Vol=34 m³, Design P=80 bar gauge", x: 4600, y: 2400 }
    ],
    qaKnowledge: {
      sampleQuestions: [
        "What is the emergency depressurization sequence on high reactor bed temperature?",
        "Where are the catalyst quench hydrogen injection points located?",
        "Explain the high-to-low pressure emergency isolation trip interlock (XV-301)."
      ],
      summary: "Removes sulfur and nitrogen from straight-run diesel using high-pressure hydrogen over CoMo/NiMo catalyst beds at 65 bar. Features safety-instrumented emergency depressuring valves to blowdown drum.",
      operatingEnvelope: "Reactor Inlet: 345 °C | Reactor Operating P: 65 bar gauge | Hydrogen to Oil Ratio: 350 Nm³/m³",
      isolationPoints: [
        "Reactor R-301 emergency depressurization valve BDV-301 (Fail-Open to Flare)",
        "Recycle gas compressor suction ESD-301 quick-closing double flanged valve"
      ]
    }
  },
  {
    id: "4",
    tag: "PID-105",
    title: "Product rundown and storage",
    unit: "Unit 400 - Rundown and tankage",
    thumb: "/pid-corpus/4-thumb.jpg",
    display: "/pid-corpus/4-display.jpg",
    width: 7168,
    height: 4562,
    node_count: 556,
    edge_count: 605,
    dwgNumber: "DWG: 4404-TK-401",
    revision: "REV C",
    sheet: "SHEET 01 / 03",
    description: "Refined hydrocarbon product rundown manifolds, on-line custody transfer analyzer loop, and atmospheric storage tank headers.",
    labels: {
      crossing: 107,
      general: 45,
      connector: 293,
      instrumentation: 35,
      valve: 67,
      arrow: 5,
      background: 4
    },
    keyEquipment: [
      { tag: "TK-401", type: "Atmospheric Tank", description: "Finished Low-Sulfur Diesel Storage Tank", specs: "Vol=25,000 m³, Internal Floating Roof, API 650", x: 4800, y: 1800 },
      { tag: "TK-402", type: "Atmospheric Tank", description: "Finished Heavy Naphtha Storage Tank", specs: "Vol=18,000 m³, Aluminum Domed Floating Roof", x: 4800, y: 3200 },
      { tag: "P-401A", type: "Product Export Pump", description: "Pipeline Custody Transfer Shipping Pump", specs: "Q=450 m³/h, Head=120 m, 250 kW Motor", x: 2200, y: 2600 },
      { tag: "FCV-401", type: "Custody Flow Control", description: "Turbine Meter Flow Prover Control Valve", specs: "10\" ANSI 150 Cage Guided", x: 3100, y: 2600 }
    ],
    qaKnowledge: {
      sampleQuestions: [
        "What safety interlock prevents tank TK-401 overfill?",
        "Where is the on-line flash point and sulfur analyzer loop tapped?",
        "What is the maximum pumping rate to the export marine terminal?"
      ],
      summary: "Distributes finished on-spec refinery streams into bulk tankage farm. Incorporates automatic radar tank gauging, high-high level alarm trips, and custody-transfer Coriolis meter runs.",
      operatingEnvelope: "Max Transfer Rate: 450 m³/h | Flash Point: > 55 °C | Max Storage Temperature: 38 °C",
      isolationPoints: [
        "Tank dyke wall perimeter containment isolation valves (Normally Closed)",
        "Overfill prevention safety shut-off valve (SIL-2 certified, spring return)"
      ]
    }
  }
];

export interface DigitizationStageLog {
  stage: number;
  label: string;
  durationMs: number;
  logText: string;
  detail: string;
}

export const DIGITIZATION_STAGES: DigitizationStageLog[] = [
  {
    stage: 1,
    label: "Model Weight Initialization",
    durationMs: 2800,
    logText: "Loading YOLO model from models/weights/pid/best.pt...",
    detail: "Initialized TensorRT engine backend (FP16 optimized). Enclave VRAM allocated: 1,840 MB."
  },
  {
    stage: 2,
    label: "Legend & Taxonomy Verification",
    durationMs: 2600,
    logText: "Active legend: Refinery_PSU_Taxonomy_v1",
    detail: "Validated 14 standard ISA-5.1 symbol classes: valves, pumps, vessels, exchangers, bubbles, crossings."
  },
  {
    stage: 3,
    label: "Optical Character Recognition",
    durationMs: 2200,
    logText: "Extracted tag and label text entities via EasyOCR",
    detail: "Detected alphanumeric equipment tags, piping diameters, line specs, and revision annotations."
  },
  {
    stage: 4,
    label: "Topological Skeleton Line Tracing",
    durationMs: 3200,
    logText: "Tracing skeleton line topology and orthogonal line junctions...",
    detail: "Constructing adjacency matrix across process streams, instrument leads, and electrical conduits."
  },
  {
    stage: 5,
    label: "GraphML & JSON Serialization",
    durationMs: 2600,
    logText: "Exporting validated topology to GraphML schema and symbol JSON ledger...",
    detail: "Sovereign SHA-256 integrity hash stamped. 0 bytes cloud egress. Ready for query analysis."
  }
];
