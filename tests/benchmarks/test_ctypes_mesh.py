"""Test: can we access Blender's internal C functions via ctypes?"""
import ctypes, sys, os

# On macOS, RTLD_DEFAULT searches all loaded libraries including main executable
# Blender symbols are in the main executable
RTLD_DEFAULT = ctypes.c_void_p(-2)  # macOS RTLD_DEFAULT

# Try to find basic Blender C API symbols
lib = ctypes.CDLL(None, mode=ctypes.RTLD_GLOBAL)  # None = current process

# List some known Blender symbols
sym_names = [
    "BKE_mesh_new_nomain",
    "BKE_mesh_new_nomain_from_template",
    "BKE_id_new",
    "BKE_id_new_nomain",
    "BKE_libblock_alloc",
    "BKE_main_namemap_validate",
    "G_main",
    "DNA_mesh_types_register",
]

print("Checking for Blender symbols via dlsym...")
# Use actual dlsym
libc = ctypes.CDLL("libSystem.dylib")
libc.dlsym.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
libc.dlsym.restype = ctypes.c_void_p

for name in sym_names:
    ptr = libc.dlsym(RTLD_DEFAULT, name.encode())
    if ptr:
        print(f"  FOUND: {name} at {hex(ptr)}")
    else:
        print(f"  NOT FOUND: {name}")

# Also try to get G_main (the main database pointer)
ptr = libc.dlsym(RTLD_DEFAULT, b"G_main")
if ptr:
    print(f"\nG_main found! Pointer: {hex(ptr)}")
else:
    # Try alternative
    for alt in ["G_MAIN", "_G_main"]:
        ptr = libc.dlsym(RTLD_DEFAULT, alt.encode())
        if ptr:
            print(f"Found {alt}: {hex(ptr)}")
