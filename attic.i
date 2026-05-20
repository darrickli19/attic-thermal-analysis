insulation_thickness = 0.406

[Mesh]
    [Ceiling]
        type = GeneratedMeshGenerator
        dim = 2
        nx = 200
        ny = 20
        xmax = ${fparse insulation_thickness + 0.016}
        ymax = 0.1
    []
    [Insulation_Block]
        type = SubdomainBoundingBoxGenerator
        input = Ceiling
        block_id = 1
        block_name = Insulation
        bottom_left = '0 0 0'
        top_right = '${insulation_thickness} 0.1 0'
    []
    [Drywall_Block]
        type = SubdomainBoundingBoxGenerator
        input = Insulation_Block
        block_id = 2
        block_name = Drywall
        bottom_left = '${insulation_thickness} 0 0'
        top_right = '${fparse insulation_thickness + 0.016} 0.1 0'
    []
[]

[Variables]
    [Temperature]
        initial_condition = 24.44
    []
[]

[Kernels]
    [heat_conduction]
        type = HeatConduction
        variable = Temperature
    []
    [heat_conduction_time_derivative]
        type = HeatConductionTimeDerivative
        variable = Temperature
    []
[]

[Materials]
    [Insulation]
        type = HeatConductionMaterial
        thermal_conductivity = 0.04
        specific_heat = 840
        block = Insulation
    []
    [Insulation_density]
        type = GenericConstantMaterial
        prop_names = 'density'
        prop_values = '16'
        block = Insulation
    []
    [Drywall]
        type = HeatConductionMaterial
        thermal_conductivity = 0.17
        specific_heat = 1090
        block = Drywall
    []
    [Drywall_density]
        type = GenericConstantMaterial
        prop_names = 'density'
        prop_values = '784'
        block = Drywall
    []
[]

[Functions]
    [sensor2_temperature]
        type = PiecewiseLinear
        data_file = data/sensor2_bc.csv
        format = columns
        x_index_in_file = 0
        y_index_in_file = 1
    []
[]

[BCs]
    [Hot]
        type = FunctionDirichletBC
        variable = Temperature
        boundary = left
        function = sensor2_temperature
    []
    [Cold]
        type = ConvectiveHeatFluxBC
        variable = Temperature
        boundary = right
        T_infinity = 24.44
        heat_transfer_coefficient = 5.0
    []
[]

[Problem]
    type = FEProblem
[]

[Executioner]
    type = Transient
    solve_type = NEWTON
    petsc_options_iname = '-pc_type -pc_hypre_type'
    petsc_options_value = 'hypre boomeramg'
    dt = 60
    end_time = 86340
    [TimeIntegrator]
        type = CrankNicolson
    []
[]

[Outputs]
    csv = true
    exodus = true
[]