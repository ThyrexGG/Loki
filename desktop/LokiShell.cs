// Win32 helpers that give the Loki app window its own taskbar identity.
// Edge --app windows normally group under Edge's AppUserModelID, so the taskbar shows the Edge icon.
// Setting a Loki AppUserModelID on both the Start Menu/Desktop shortcuts and the window makes Windows
// group the window as "Loki" and use the shortcut's icon; WM_SETICON also sets the title-bar icon.
// Loaded with Add-Type by Loki.ps1 and Install_Shortcuts.ps1 (compiled by the built-in .NET Framework).
using System;
using System.Runtime.InteropServices;

public static class LokiShell
{
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    public struct PROPERTYKEY
    {
        public Guid fmtid;
        public uint pid;
        public PROPERTYKEY(Guid g, uint p) { fmtid = g; pid = p; }
    }

    [StructLayout(LayoutKind.Explicit, Size = 16)]
    public struct PROPVARIANT
    {
        [FieldOffset(0)] public ushort vt;
        [FieldOffset(8)] public IntPtr p;
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore
    {
        void GetCount(out uint count);
        void GetAt(uint index, out PROPERTYKEY key);
        void GetValue(ref PROPERTYKEY key, out PROPVARIANT value);
        void SetValue(ref PROPERTYKEY key, ref PROPVARIANT value);
        void Commit();
    }

    [ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPersistFile
    {
        void GetClassID(out Guid clsid);
        [PreserveSig] int IsDirty();
        void Load([MarshalAs(UnmanagedType.LPWStr)] string file, uint mode);
        void Save([MarshalAs(UnmanagedType.LPWStr)] string file, [MarshalAs(UnmanagedType.Bool)] bool remember);
        void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string file);
        void GetCurFile(out IntPtr file);
    }

    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    class CShellLink { }

    [DllImport("shell32.dll")]
    static extern int SHGetPropertyStoreForWindow(IntPtr hwnd, ref Guid iid, [MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr LoadImage(IntPtr hinst, string name, uint type, int cx, int cy, uint flags);

    [DllImport("user32.dll")]
    static extern IntPtr SendMessage(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);

    static readonly Guid AppUserModelFmt = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");
    const uint PID_RelaunchCommand = 2, PID_RelaunchIcon = 3, PID_RelaunchName = 4, PID_ID = 5;

    static void SetString(IPropertyStore store, uint pid, string value)
    {
        var key = new PROPERTYKEY(AppUserModelFmt, pid);
        var pv = new PROPVARIANT { vt = 31 /* VT_LPWSTR */, p = Marshal.StringToCoTaskMemUni(value) };
        try { store.SetValue(ref key, ref pv); }
        finally { Marshal.FreeCoTaskMem(pv.p); }
    }

    /// Stamp a .lnk shortcut with an AppUserModelID.
    public static void SetShortcutAppId(string lnkPath, string appId)
    {
        object link = new CShellLink();
        try
        {
            var file = (IPersistFile)link;
            file.Load(lnkPath, 2 /* STGM_READWRITE */);
            var store = (IPropertyStore)link;
            SetString(store, PID_ID, appId);
            store.Commit();
            file.Save(lnkPath, true);
        }
        finally { Marshal.ReleaseComObject(link); }
    }

    /// Give a top-level window the Loki AppUserModelID (relaunch props must be set before the ID).
    public static void SetWindowAppId(IntPtr hwnd, string appId, string relaunchCommand, string iconPath, string displayName)
    {
        Guid iid = typeof(IPropertyStore).GUID;
        IPropertyStore store;
        Marshal.ThrowExceptionForHR(SHGetPropertyStoreForWindow(hwnd, ref iid, out store));
        try
        {
            SetString(store, PID_RelaunchCommand, relaunchCommand);
            SetString(store, PID_RelaunchIcon, iconPath + ",0");
            SetString(store, PID_RelaunchName, displayName);
            SetString(store, PID_ID, appId);
            store.Commit();
        }
        finally { Marshal.ReleaseComObject(store); }
    }

    /// Set the window's title-bar / Alt+Tab icons. The HICONs live as long as the calling process,
    /// which is why Loki.ps1 keeps running until the window closes.
    public static void SetWindowIcon(IntPtr hwnd, string icoPath)
    {
        const uint IMAGE_ICON = 1, LR_LOADFROMFILE = 0x10, WM_SETICON = 0x80;
        IntPtr big = LoadImage(IntPtr.Zero, icoPath, IMAGE_ICON, 48, 48, LR_LOADFROMFILE);
        IntPtr small = LoadImage(IntPtr.Zero, icoPath, IMAGE_ICON, 16, 16, LR_LOADFROMFILE);
        if (big != IntPtr.Zero) SendMessage(hwnd, WM_SETICON, (IntPtr)1, big);
        if (small != IntPtr.Zero) SendMessage(hwnd, WM_SETICON, (IntPtr)0, small);
    }
}
