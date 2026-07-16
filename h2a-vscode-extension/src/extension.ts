import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';
import { execFile, exec } from 'child_process';
import { WebviewPanelProvider } from './webview';

function ensurePythonEnv(h2aMvpPath: string): Thenable<string> {
    const isWindows = os.platform() === 'win32';
    const pythonCmd = isWindows ? 'python' : 'python3';
    const binDir = isWindows ? 'Scripts' : 'bin';
    const pythonExe = isWindows ? 'python.exe' : 'python';
    const pipExe = isWindows ? 'pip.exe' : 'pip';
    
    const pythonPath = path.join(h2aMvpPath, '.venv', binDir, pythonExe);
    if (fs.existsSync(pythonPath)) {
        return Promise.resolve(pythonPath);
    }

    return vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: "Setting up Python Environment (First-time run)...",
        cancellable: false
    }, async (progress) => {
        return new Promise<string>((resolve, reject) => {
            progress.report({ message: "Creating virtual environment (.venv)..." });
            
            exec(`${pythonCmd} -m venv .venv`, { cwd: h2aMvpPath }, (venvError, stdout, stderr) => {
                if (venvError) {
                    vscode.window.showErrorMessage(`Failed to create python virtual environment: ${stderr || venvError.message}`);
                    reject(venvError);
                    return;
                }

                progress.report({ message: "Installing packages (pip install -r requirements.txt)..." });
                const pipPath = path.join(h2aMvpPath, '.venv', binDir, pipExe);
                exec(`"${pipPath}" install -r requirements.txt`, { cwd: h2aMvpPath }, (pipError, pipStdout, pipStderr) => {
                    if (pipError) {
                        vscode.window.showErrorMessage(`Failed to install requirements: ${pipStderr || pipError.message}`);
                        reject(pipError);
                        return;
                    }

                    vscode.window.showInformationMessage("H2A Migrator Python environment initialized successfully!");
                    resolve(pythonPath);
                });
            });
        });
    });
}

export function activate(context: vscode.ExtensionContext) {
    console.log('SAP Hybris to Salesforce Apex Migrator Extension is now active.');

    let translateCommand = vscode.commands.registerCommand('h2a-migrator.translateFolder', async (uri: vscode.Uri) => {
        if (!uri) {
            vscode.window.showErrorMessage('No folder selected for translation.');
            return;
        }

        let inputPath = uri.fsPath;
        try {
            const stat = await vscode.workspace.fs.stat(uri);
            if (stat.type !== vscode.FileType.Directory) {
                inputPath = path.dirname(inputPath);
            }
        } catch (e) {
            // Fallback to simple dirname if fs.stat fails
            inputPath = path.dirname(inputPath);
        }

        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            vscode.window.showErrorMessage('No workspace open.');
            return;
        }

        // Read extension configuration settings
        const extConfig = vscode.workspace.getConfiguration('h2aMigrator');
        let h2aMvpPath: string = extConfig.get<string>('pipelinePath') || '';
        let pythonPath: string = extConfig.get<string>('pythonPath') || '';
        let anthropicApiKey: string = extConfig.get<string>('anthropicApiKey') || '';
        let openrouterApiKey: string = extConfig.get<string>('openrouterApiKey') || '';
        let provider: string = extConfig.get<string>('provider') || 'anthropic';
        let incrementalMode: boolean = extConfig.get<boolean>('incrementalMode') ?? true;
        let customModel: string = extConfig.get<string>('customModel') || '';
        let engine: string = extConfig.get<string>('engine') || 'agentic';
        let verifyDeploy: boolean = extConfig.get<boolean>('verifyDeploy') ?? false;

        if (!h2aMvpPath) {
            // Check if there is a bundled h2a-mvp folder in the extension
            const bundledPath = path.join(context.extensionPath, 'h2a-mvp');
            if (fs.existsSync(bundledPath)) {
                h2aMvpPath = bundledPath;
            } else {
                // Find the absolute path to the h2a-mvp directory dynamically
                let currentPath = inputPath;
                while (currentPath && path.basename(currentPath) !== 'h2a-mvp' && currentPath !== path.dirname(currentPath)) {
                    currentPath = path.dirname(currentPath);
                }

                if (path.basename(currentPath) === 'h2a-mvp') {
                    h2aMvpPath = currentPath;
                } else {
                    const workspaceFolder = workspaceFolders[0].uri.fsPath;
                    if (path.basename(workspaceFolder) === 'h2a-mvp') {
                        h2aMvpPath = workspaceFolder;
                    } else {
                        h2aMvpPath = path.join(workspaceFolder, 'h2a-mvp');
                    }
                }
            }
        }

        // Ensure Python virtual environment exists
        let resolvedPythonPath = pythonPath;
        if (!resolvedPythonPath) {
            try {
                resolvedPythonPath = await ensurePythonEnv(h2aMvpPath);
            } catch (e: any) {
                vscode.window.showErrorMessage(`Failed to initialize H2A python environment: ${e.message}`);
                return;
            }
        }

        const outputDirName = `salesforce_${path.basename(inputPath)}`;
        const outputPath = path.join(path.dirname(inputPath), outputDirName);
        const scriptCwd = h2aMvpPath;

        if (!fs.existsSync(resolvedPythonPath)) {
            vscode.window.showErrorMessage(`Python environment not found at: ${resolvedPythonPath}. Please verify your setting 'h2aMigrator.pythonPath' or run 'make setup' inside: ${h2aMvpPath}`);
            return;
        }

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "Translating Hybris Slice...",
            cancellable: false
        }, async (progress) => {
            return new Promise<void>((resolve, reject) => {
                progress.report({ message: "Running ingestion & generation..." });

                // Spawns python -m src.main <engine> --input ... --output ...
                //   agentic → agent-migrate (Planner + Builder + Critic + Verifier + RAG)
                //   linear  → repo-migrate  (the deterministic pipeline)
                const command = engine === 'linear' ? 'repo-migrate' : 'agent-migrate';
                const argsRun = ['-m', 'src.main', command, '--input', inputPath, '--output', outputPath];
                if (verifyDeploy) {
                    // Validate-only deploy to the default Salesforce org + self-heal (see README).
                    argsRun.push('--verify');
                    progress.report({ message: "Verification enabled — will deploy to your default org (check-only)..." });
                }

                const envObj: any = { ...process.env, PYTHONIOENCODING: 'utf-8' };
                if (anthropicApiKey) {
                    envObj['ANTHROPIC_API_KEY'] = anthropicApiKey;
                }
                if (openrouterApiKey) {
                    envObj['OPENROUTER_API_KEY'] = openrouterApiKey;
                }
                if (provider) {
                    envObj['H2A_PROVIDER'] = provider;
                }
                envObj['H2A_INCREMENTAL'] = incrementalMode ? "true" : "false";
                if (customModel) {
                    envObj['H2A_CUSTOM_MODEL'] = customModel;
                }

                execFile(resolvedPythonPath, argsRun, { 
                    cwd: scriptCwd,
                    env: envObj
                }, (error: any, stdout: string, stderr: string) => {
                    if (error) {
                        vscode.window.showErrorMessage(`Translation failed: ${stderr || error.message}`);
                        reject(error);
                        return;
                    }

                    // Spawns python -m src.main metadata --input ... --output ...
                    const argsMeta = ['-m', 'src.main', 'metadata', '--input', inputPath, '--output', outputPath];
                    
                    execFile(resolvedPythonPath, argsMeta, { 
                        cwd: scriptCwd,
                        env: envObj
                    }, (metaError: any, metaStdout: string, metaStderr: string) => {
                        let finalLog = stdout;
                        if (metaError) {
                            vscode.window.showWarningMessage(`Metadata compilation skipped: ${metaStderr || metaError.message}`);
                        } else {
                            vscode.window.showInformationMessage(`Successfully generated database schemas & relationship lookups!`);
                            finalLog += '\n' + metaStdout;
                        }

                        vscode.window.showInformationMessage(`Successfully translated slice to: ${outputPath}`);
                        
                        // Show Webview Panel with combined status reports
                        WebviewPanelProvider.createOrShow(context.extensionUri, finalLog, outputPath);
                        resolve();
                    });
                });
            });
        });
    });

    context.subscriptions.push(translateCommand);
}

export function deactivate() {}
