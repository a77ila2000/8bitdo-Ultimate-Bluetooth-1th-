// SPDX-License-Identifier: MIT
// Original manufacturer's ABI/boot command; no flash protocol replacement.
using System;
using System.IO;
using System.Management;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using System.Diagnostics;

class FlashTool {
    const string Dll="8BitDoFirmwareUpdaterTools.dll";
    const string DllHash="b38ffa61b12af29d41dc55212e5ba44e509130facf6e3c4db9a7141aa313f974";
    static readonly string Root=AppDomain.CurrentDomain.BaseDirectory;
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate void ErrorCallback();
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate void TextCallback(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate void PidCallback(int a,int b);
    [DllImport(Dll,EntryPoint="_Callback@4",ExactSpelling=true,CallingConvention=CallingConvention.StdCall)] static extern void OnError(ErrorCallback cb);
    [DllImport(Dll,EntryPoint="_CallbackString@4",ExactSpelling=true,CallingConvention=CallingConvention.StdCall)] static extern void OnText(TextCallback cb);
    [DllImport(Dll,EntryPoint="_CallbackChangeErrorPID@4",ExactSpelling=true,CallingConvention=CallingConvention.StdCall)] static extern void OnPid(PidCallback cb);
    [DllImport(Dll,EntryPoint="FindHid",ExactSpelling=true,CallingConvention=CallingConvention.Cdecl)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool Find(ushort vid,ushort pid);
    [DllImport(Dll,EntryPoint="Open_Hid",ExactSpelling=true,CallingConvention=CallingConvention.Cdecl)] [return:MarshalAs(UnmanagedType.Bool)] static extern bool Open();
    [DllImport(Dll,EntryPoint="_WriteHidAdvance@8",ExactSpelling=true,CallingConvention=CallingConvention.StdCall)] static extern uint Write([In] byte[] b,uint n);
    [DllImport(Dll,EntryPoint="_updateGampeWithFile@4",ExactSpelling=true,CallingConvention=CallingConvention.StdCall,CharSet=CharSet.Unicode)] static extern void Update([MarshalAs(UnmanagedType.LPWStr)] string path);
    [DllImport(Dll,EntryPoint="_dll_getProgress@0",ExactSpelling=true,CallingConvention=CallingConvention.StdCall)] static extern int Progress();
    [DllImport("kernel32",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr LoadLibraryEx(string path,IntPtr unused,uint flags);
    static volatile bool error;
    static readonly ErrorCallback E=delegate{error=true;Console.WriteLine("ERROR callback");};
    static readonly TextCallback T=delegate(IntPtr p){error=true;Console.WriteLine("ERROR vendor callback");};
    static readonly PidCallback P=delegate(int a,int b){error=true;Console.WriteLine("ERROR model mismatch {0:x}/{1:x}",a,b);};
    static string Hash(string path){using(var f=File.OpenRead(path))using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(f)).Replace("-","").ToLowerInvariant();}
    static string Expected(string name) {
        switch(name) {
            case "controller-conservative":return "78d7364aad506d5c7b33fa0db5712524bc8f1f0a49fe57f9a43e90b4a198b0b7";
            case "controller-enhanced":return "dee297b7c1a5f0b0646f05fc16f792be94df1e52cc478338f1780612fd897767";
            case "receiver-2ms":return "e47eb1b0eddcd817f03573671f58e98c452387ba67aff01e8852229d39c1ce95";
            case "RESTORE-controller-v1.11":return "1030145fec364aceb55ceaed221396131dcf02eaaeeb8bd9ad4044ba5596074d";
            case "RESTORE-receiver-v1.04":return "099101a6ca62321b76de2b7c61452342be794956a622aba542120125d91ffb97";
            default:throw new Exception("Unknown/unapproved variant; historical timing and diagnostic images cannot be flashed with this tool");
        }
    }
    static bool Controller(string name){return name.Contains("controller");}
    static string Validate(string name) {
        string expected=Expected(name), path=Path.Combine(Root,"output",name+".dat");
        if(Hash(path)!=expected)throw new Exception("Firmware hash mismatch");
        byte[] b=File.ReadAllBytes(path); bool controller=Controller(name);
        uint size=controller?(name=="controller-enhanced"?105472u:104960u):262144u;
        if(b.Length!=size+28 || BitConverter.ToUInt32(b,0)!=(controller?111u:104u) ||
           BitConverter.ToUInt32(b,4)!=(controller?0x01018000u:0x3000u) ||
           BitConverter.ToUInt32(b,8)!=size || BitConverter.ToUInt32(b,12)!=(controller?0x6007u:0x6008u))throw new Exception("Firmware header mismatch");
        Console.WriteLine("IMAGE {0}.dat SHA256 {1}",name,expected);return path;
    }
    static ushort Single(bool allowMissing=false) {
        int count=0;ushort pid=0;
        using(var q=new ManagementObjectSearcher("SELECT PNPDeviceID FROM Win32_PnPEntity WHERE Present=TRUE"))
        foreach(ManagementObject item in q.Get()) {
            string id=Convert.ToString(item["PNPDeviceID"]).ToUpperInvariant();
            if(id.StartsWith("USB\\VID_2DC8&PID_") && id.IndexOf('\\',4)>0) {
                // Count parent USB devices, not composite interface children.
                int slash=id.IndexOf('\\',4);string hardware=id.Substring(4,slash-4);
                if(hardware.Contains("&MI_"))continue;
                count++;pid=Convert.ToUInt16(id.Substring(17,4),16);
            }
        }
        if(count==0 && allowMissing)return 0;
        if(count!=1)throw new Exception("Connect exactly ONE 8BitDo USB device; found "+count);
        return pid;
    }
    static void CheckRuntime() {
        if(IntPtr.Size!=4)throw new Exception("x86 runtime required");
        string dir=Path.Combine(Root,"vendor-runtime"), dll=Path.Combine(dir,Dll);
        if(Hash(dll)!=DllHash)throw new Exception("Wrong vendor DLL; run PatchTool.exe prepare");
        foreach(string name in new[]{"versions.txt","debugLog.txt","updateLog.txt","Autoupdate.exe","ICSharpCode.SharpZipLib.dll"})
            if(!File.Exists(Path.Combine(dir,"data",name)))throw new Exception("Incomplete manufacturer data folder; run PatchTool.exe prepare before loading the DLL");
        Environment.CurrentDirectory=dir;
        if(LoadLibraryEx(dll,IntPtr.Zero,0x1100)==IntPtr.Zero)throw new Exception("Cannot load pinned manufacturer DLL: "+Marshal.GetLastWin32Error());
    }
    static void Identify(bool controller) {
        var start=new ProcessStartInfo(Path.Combine(Root,"PatchTool.exe"),"identify "+(controller?"controller":"receiver"));
        start.UseShellExecute=false;start.CreateNoWindow=true;
        using(var p=Process.Start(start)) {
            if(!p.WaitForExit(20000)){p.Kill();throw new Exception("Read-only identity check timed out; no flash started");}
            if(p.ExitCode!=0)throw new Exception("Boot identity did not match target. No flash started; do not force model checks");
        }
    }
    static int Main(string[] args) {
        try {
            if(args.Length==2 && args[0]=="--validate-image"){Validate(args[1]);return 0;}
            if(args.Length==1 && args[0]=="--check-runtime"){CheckRuntime();Console.WriteLine("RUNTIME hash/load OK; no hardware calls");return 0;}
            string name;
            if(args.Length==0) {
                Console.WriteLine("80NA / Ultimate Bluetooth FIRST generation ONLY. Read docs/UPDATING.ko.md.");
                Console.WriteLine("1 ADC+battery only\n2 Enhanced controller\n3 Receiver IN2ms\n4 Restore controller1.11\n5 Restore receiver1.04");
                string choice=Console.ReadLine();
                string[] names={"controller-conservative","controller-enhanced","receiver-2ms","RESTORE-controller-v1.11","RESTORE-receiver-v1.04"};
                int n;if(!int.TryParse(choice,out n)||n<1||n>5)throw new Exception("Cancelled");name=names[n-1];
            } else if(args.Length==1)name=args[0];else throw new Exception("Choose a known variant");
            string path=Validate(name);bool controller=Controller(name);
            Console.WriteLine("Disconnect all other8BitDo USB devices. Close vendor GUI/Ultimate Software.");
            Console.WriteLine("Experimental firmware. No long-session power-off fix or500Hz guarantee. Type80NA to confirm exact model:");
            if(Console.ReadLine()!="80NA")throw new Exception("Cancelled");
            CheckRuntime();ushort pid=Single();
            OnError(E);OnText(T);OnPid(P);
            if(pid!=0x3208) {
                if(!(pid==0x6007 || (!controller && pid==0x3109)))
                    throw new Exception("Expected configuration6007 or receiver standby3109. For controller: power off, hold L+R, reconnect USB to enter3208");
                if(!Find(0x2dc8,pid)||!Open())throw new Exception("Cannot open configuration HID");
                byte[] boot=new byte[64];boot[0]=0x81;boot[1]=5;boot[3]=0x51;
                if(Write(boot,64)!=1)throw new Exception("Standard boot command failed");
                for(int attempt=0;attempt<20;attempt++){Thread.Sleep(250);pid=Single(true);if(pid==0x3208)break;}
            }
            if(pid!=0x3208)throw new Exception("ROM updater3208 not found; no flash started");
            Identify(controller);
            if(Single()!=0x3208)throw new Exception("Device changed during identity check");
            if(Hash(path)!=Expected(name))throw new Exception("Image changed before flash");
            Console.WriteLine("Verified model and image. Type FLASH to start writing:");
            if(Console.ReadLine()!="FLASH")throw new Exception("Cancelled before writing");
            if(Single()!=0x3208)throw new Exception("Device changed before writing");
            Identify(controller);
            ConsoleCancelEventHandler cancel=delegate(object sender,ConsoleCancelEventArgs e){e.Cancel=true;Console.WriteLine("Writing: do not unplug or interrupt.");};
            Console.CancelKeyPress+=cancel;
            Task task=Task.Factory.StartNew(()=>Update(path));int highest=0,last=-1;
            while(!task.Wait(500)){int p=Progress();highest=Math.Max(highest,p);if(p!=last){Console.WriteLine("PROGRESS {0}",p);last=p;}}
            highest=Math.Max(highest,Progress());Console.CancelKeyPress-=cancel;
            GC.KeepAlive(E);GC.KeepAlive(T);GC.KeepAlive(P);
            if(highest!=100||error)throw new Exception("Transfer not confirmed. Keep device connected; see recovery instructions");
            Console.WriteLine("Transfer100%, no error callback. Reconnect normally, then test input. This is not a full readback or stability test.");
            return 0;
        } catch(Exception e){Console.WriteLine("STOP: "+e.Message);return 2;}
    }
}
