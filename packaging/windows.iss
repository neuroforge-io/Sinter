#ifndef AppVersion
  #define AppVersion "0.4.0"
#endif
#ifndef TargetArch
  #define TargetArch "x64"
#endif
[Setup]
AppId=io.neuroforge.sinter.{#TargetArch}
AppName=Sinter
AppVersion={#AppVersion}
AppPublisher=NeuroForge
AppPublisherURL=https://neuroforge.io
AppSupportURL=https://github.com/neuroforge-io/Sinter/issues
DefaultDirName={localappdata}\Programs\Sinter
DefaultGroupName=Sinter
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=Sinter-{#AppVersion}-windows-{#TargetArch}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\build\sinter.ico
UninstallDisplayIcon={app}\Sinter.exe
LicenseFile=..\LICENSE
MinVersion=10.0
#if TargetArch == "x64"
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#elif TargetArch == "arm64"
ArchitecturesAllowed=arm64
ArchitecturesInstallIn64BitMode=arm64
#else
ArchitecturesAllowed=x86compatible
#endif
[Files]
Source: "..\dist\Sinter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Sinter"; Filename: "{app}\Sinter.exe"
Name: "{autodesktop}\Sinter"; Filename: "{app}\Sinter.exe"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\Sinter.exe"; Description: "Open Sinter"; Flags: nowait postinstall skipifsilent
