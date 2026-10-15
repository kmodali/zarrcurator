
realmDict = {
    "dimensions" : [ 
        "time", "pfull", "phalf", "zghalf", "delhi", "depth_full", "depth_half", "dzghalf", "level_full", "level_half" ],
    
    "atmosphere" : [
        "cli",  "clivi",  "cllvi",  "clw",    "crs",
        "hfls", "hfss",  "hus",
        "pr", "pres_msl", "pres_sfc", "prls", "prw",
        "qg",  "qgvi",  "qr",  "qrvi",  "qs",  "qsvi",  "qv2m",
        "rlds",  "rlus",  "rlut",  "rsds",  "rsdt",  "rsus",  "rsut",
        "sic",   "sit",   "sfcwind",   
        "ta", "tas", "tauu", "tauv",  "ts",
        "ua", "uas", 
        "va", "vas", 
        "wa_phy",
        "zg"
    ],
    "ocean" : [
        "atmos_fluxes_FrshFlux_Evaporation",
        "atmos_fluxes_FrshFlux_Precipitation",
        "atmos_fluxes_FrshFlux_Runoff",
        "atmos_fluxes_FrshFlux_SnowFall",
        "atmos_fluxes_HeatFlux_Latent",
        "atmos_fluxes_HeatFlux_LongWave",
        "atmos_fluxes_HeatFlux_Sensible",
        "atmos_fluxes_HeatFlux_ShortWave",
        "atmos_fluxes_HeatFlux_Total",
        "atmos_fluxes_stress_x",
        "atmos_fluxes_stress_xw",
        "atmos_fluxes_stress_y",
        "atmos_fluxes_stress_yw",
        "conc",
        "ocean_fraction_depth_full",
        "ocean_fraction_depth_half",
        "ocean_fraction_surface",
        "hi", "hs",
        "heat_content_seaice",
        "heat_content_snow",
        "heat_content_total",
        "heatOceI",
        "heatOceW",
        "ice_u",
        "ice_v",
        "mlostst",
        "newice",
        "snow_to_ice",
        "so",
        "stretch_c",
        "tke", "to",
        "u", "v", "w",
        "u_vint", "v_vint",
        "zos"
    ],
    "land" : [
        "hydro_canopy_cond_limited_box",
        "hydro_snow_soil_dens_box",
        "hydro_discharge_ocean_box",
        "hydro_transpiration_box",
        "hydro_drainage_box",
        "hydro_weq_snow_box",
        "hydro_ice_soil_sl_box",
        "hydro_wtr_soil_sl_box",
        "hydro_runoff_box",
        "soil_depth_water_level",
        "soil_depth_energy_level",
        "sse_t_soil_sl_box",
        "seb_forc_hflx_box", 
        "sse_grnd_hflx_old_box", 
        "seb_heat_cap_box",
    ],
    "biogeo" : []
}

total = 0
for k,v in realmDict.items():
    print(f"realm: {k} var count:{len(v)}")
    total += len(v)

print(f"Total vars : {total}")