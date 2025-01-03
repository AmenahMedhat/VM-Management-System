import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import docker
import os
import requests
from pathlib import Path
import subprocess
import atexit
from docker.errors import DockerException


# Initialize Docker client
client = docker.from_env()
client.ping()
app_directory = os.path.dirname(os.path.abspath(__file__))

# Get the Downloads directory
def get_downloads_path():
    return os.path.join(os.path.expanduser("~"), "Downloads")

# Helper function for logging
def log_message(log_widget, message):
    log_widget.config(state="normal")
    log_widget.insert("end", message + "\n")
    log_widget.yview("end")  # Auto-scroll to the latest log
    log_widget.config(state="disabled")
    


def create_image(name, size, location):
    # Ensure the directory exists, create it if it doesn't
    if not os.path.exists(location):
        os.makedirs(location)
    
    # Construct the command to create the image
    image_path = os.path.join(location, f"{name}.img")
    cmd = f"qemu-img create -f qcow2 {image_path} {size}M"
    
    try:
        # Run the command and capture the output
        result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Print or log the output (stdout and stderr)
        print(result.stdout.decode())  # Command output
        print(result.stderr.decode())  # Command errors (if any)
        
        return image_path
    except subprocess.CalledProcessError as e:
        # If the command fails, handle the error
        print(f"Error creating image: {e}")
        print(f"stdout: {e.stdout.decode()}")
        print(f"stderr: {e.stderr.decode()}")
        raise


def boot(ram, cores, imagefile, isofile):
    cmd = (
        "qemu-system-x86_64 "
        f"-m {ram} "
        "-boot d "
        "-enable-kvm "
        f"-smp {cores} "
        f"-hda {imagefile} "
        "-cpu host "
        "-vga virtio "
        "-display sdl,gl=on"
    )

    if isofile and isofile.lower() != "iso file (leave blank to skip)":
        cmd += f" -cdrom {isofile}"

    print(cmd)
    os.system(cmd)

created_files = [] 
def create_dockerfile(log_widget):
    loaded_files = {}  # Dictionary to store file contents: {filename: content}
    current_file = None  # Track currently displayed file
    file_labels = []  # List to keep track of file labels
     
    def validate_dockerfile(content):
             required_commands = ['FROM', 'COPY']
             found_commands = [cmd for cmd in required_commands if cmd in content]
             if len(found_commands) != len(required_commands):
                 missing = set(required_commands) - set(found_commands)
                 messagebox.showwarning("Warning", f"Missing required commands: {', '.join(missing)}")
                 return False
             return True

    def load_template(template):
        if template == "Custom":
            dockerfile_content = (
                 "# Custom Dockerfile\n"
                "FROM <base-image>\n"
                "WORKDIR /app\n"
                "COPY . .\n"
                "# Add your commands here\n"
                "CMD [\"your-command\"]\n"
            )
            additional_files = {}
           
        elif template == "Python App":
            dockerfile_content = (
                "# Python Dockerfile\n"
                "FROM python:3.9-slim\n\n"
                "WORKDIR /app\n"
                "COPY requirements.txt . \n"
                "RUN pip install --no-cache-dir -r requirements.txt\n"
                "COPY . .\n"
                "CMD [\"python\", \"app.py\"]\n"
            )
            additional_files = {
                "requirements.txt": (
                    "# Example Python requirements\n"
                    "flask==2.2.3\n"
                    "requests==2.31.0\n"
                    "numpy==1.23.5\n"
                )
            }
        
        elif template == "Node.js App":
            dockerfile_content = (
                "# Node.js Dockerfile\n"
                "FROM node:16\n\n"
                "WORKDIR /app\n"
                "COPY package*.json .\n"
                "RUN npm install\n"
                "COPY . .\n"
                "CMD [\"node\", \"server.js\"]\n"
            )
            additional_files = {
                "package.json": (
                    "{\n"
                    "  \"name\": \"node-app\",\n"
                    "  \"version\": \"1.0.0\",\n"
                    "  \"description\": \"Example Node.js application\",\n"
                    "  \"main\": \"server.js\",\n"
                    "  \"scripts\": {\n"
                    "    \"start\": \"node server.js\"\n"
                    "  },\n"
                    "  \"dependencies\": {\n"
                    "    \"express\": \"^4.18.2\"\n"
                    "  }\n"
                    "}\n"
                )
            }
        elif template == "Java App":
            dockerfile_content = (
                "# Java Dockerfile\n"
                "FROM openjdk:11\n\n"
                "WORKDIR /app\n"
                "COPY pom.xml .\n"
                "COPY src/ ./src/\n"
                "RUN mvn clean install\n"
                "COPY target/myapp.jar myapp.jar\n"
                "CMD [\"java\", \"-jar\", \"myapp.jar\"]\n"
            )
            additional_files = {
                "pom.xml": (
                    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                    "<project xmlns=\"http://maven.apache.org/POM/4.0.0\"\n"
                    "         xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"\n"
                    "         xsi:schemaLocation=\"http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd\">\n"
                    "    <modelVersion>4.0.0</modelVersion>\n\n"
                    "    <groupId>com.example</groupId>\n"
                    "    <artifactId>myapp</artifactId>\n"
                    "    <version>1.0-SNAPSHOT</version>\n\n"
                    "    <dependencies>\n"
                    "        <dependency>\n"
                    "            <groupId>org.springframework.boot</groupId>\n"
                    "            <artifactId>spring-boot-starter</artifactId>\n"
                    "            <version>2.7.0</version>\n"
                    "        </dependency>\n"
                    "    </dependencies>\n\n"
                    "</project>\n"
                )
            }
        else:
            dockerfile_content = ""
            additional_files = {}

        return dockerfile_content, additional_files
    
    def add_new_file():
            filename = simpledialog.askstring("New File", "Enter filename:")
            if filename and not any(char in filename for char in '<>:"/\\|?*'):
                loaded_files[filename] = ""
                update_file_list()
                show_file(filename)
            else:
                messagebox.showerror("Error", "Invalid filename")
    
    def update_file_list():
        files_listbox.delete(0, tk.END)
        for filename in loaded_files:
            files_listbox.insert(tk.END, filename)

    def save_file(filename, content):
        try:
            file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
            with open(file_path, "w") as f:
                f.write(content)
            if file_path not in created_files:
                created_files.append(file_path)
            log_message(log_widget, f"Saved {filename}")
            messagebox.showinfo("Success", f"Saved {filename}")
        except Exception as e:
            log_message(log_widget, f"Error saving {filename}: {e}")

    def show_file(filename):
            nonlocal current_file
            current_file = filename
            additional_text.delete("1.0", "end")
            additional_text.insert("1.0", loaded_files.get(filename, ""))
            files_label.config(text=f"Current File: {filename}")

    def save_current_file():
        if current_file:
            content = additional_text.get("1.0", "end").strip()
            loaded_files[current_file] = content
            save_file(current_file, content)


    def update_file_labels():
        # Clear existing labels
        for label in file_labels:
            label.destroy()
        file_labels.clear()
        
        # Create new labels
        for filename in loaded_files.keys():
            label = ttk.Label(
                files_label, 
                text=filename,
                cursor="hand2",  # Show hand cursor on hover
                style="Link.TLabel" if filename == current_file else "TLabel"
            )
            label.bind("<Button-1>", lambda e, f=filename: show_file(f))
            label.pack(anchor="w", padx=5, pady=2)
            file_labels.append(label)
    
    def save_dockerfile():
        content = dockerfile_text.get("1.0", "end").strip()
        if content and validate_dockerfile(content):
            save_file("Dockerfile", content)

        
    def load_dockerfile():
        file_path = filedialog.askopenfilename(
            filetypes=[("Dockerfile", "Dockerfile*"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, "r") as file:
                    content = file.read()
                dockerfile_text.delete("1.0", "end")
                dockerfile_text.insert("1.0", content)
                additional_text.delete("1.0", "end") 
            except Exception as e:
                messagebox.showerror("Error", f"Could not load Dockerfile: {e}")

    def load_additional_files():
        file_paths = filedialog.askopenfilenames(
            title="Select Additional Files",
            filetypes=[("All Files", "*.*")]
        )
        if file_paths:
            for file_path in file_paths:
                try:
                    with open(file_path, "r") as file:
                        content = file.read()
                        filename = file_path.split("/")[-1]
                        loaded_files[filename] = content
                except Exception as e:
                    messagebox.showerror("Error", f"Could not load {file_path}: {e}")
            
            # Show the first loaded file
            if loaded_files and not current_file:
                show_file(list(loaded_files.keys())[0])
            else:
                update_file_labels()

    def on_template_change(*args):
        selected = template_var.get()
        dockerfile_content, template_files = load_template(selected)
        dockerfile_text.delete("1.0", "end")
        dockerfile_text.insert("1.0", dockerfile_content)
        loaded_files.clear()
        loaded_files.update(template_files)
        additional_text.delete("1.0", "end")

        update_file_list()


    popup = tk.Toplevel()
    popup.title("Create or Edit Dockerfile")
    popup.geometry("1000x600")

    # Create a style for the "selected" label
    style = ttk.Style()
    style.configure("Link.TLabel", foreground="blue", font=("TkDefaultFont", 10, "underline"))

    # Template selection
    template_var = tk.StringVar(value="Custom")
    templates = ["Custom","Python App", "Node.js App", "Java App", "Load Existing Dockerfile"]
    ttk.Label(popup, text="Template:").pack(anchor="w", padx=10, pady=5)
    ttk.Combobox(popup, textvariable=template_var, values=templates, state="readonly").pack(anchor="w", padx=10)


    # Split layout
    frame = ttk.Frame(popup)
    frame.pack(fill="both", expand=True, padx=10, pady=10)

    # Dockerfile editor
    dockerfile_frame = ttk.LabelFrame(frame, text="Dockerfile")
    dockerfile_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)

    dockerfile_text = tk.Text(dockerfile_frame, wrap="word")
    dockerfile_text.pack(fill="both", expand=True, padx=5, pady=5)
    # Define save_dockerfile function
   
    

    dockerfile_buttons_frame = ttk.Frame(dockerfile_frame)
    dockerfile_buttons_frame.pack(fill="x", padx=5, pady=5)

    load_dockerfile_button = ttk.Button(dockerfile_buttons_frame, text="Upload Dockerfile", command=load_dockerfile)
    load_dockerfile_button.pack(side="left", padx=5)
    
    ttk.Button(dockerfile_buttons_frame, text="Save Dockerfile", command=save_dockerfile).pack(side="left", padx=5)

    # Additional files editor
    additional_frame = ttk.LabelFrame(frame, text="Additional Files")
    additional_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
    
    files_listbox = tk.Listbox(additional_frame, height=5)
    files_listbox.pack(fill="x", padx=5, pady=5)
    files_listbox.bind('<<ListboxSelect>>', 
        lambda e: show_file(files_listbox.get(files_listbox.curselection())) if files_listbox.curselection() else None)

    # Frame for file labels
    files_label = ttk.Label(additional_frame, text="Files")
    files_label.pack(fill="x", padx=5, pady=5)

    additional_text = tk.Text(additional_frame, wrap="word")
    additional_text.pack(fill="both", expand=True, padx=5, pady=5)

    # Buttons frame for additional files
    additional_buttons_frame = ttk.Frame(additional_frame)
    additional_buttons_frame.pack(fill="x", padx=5, pady=5)

    load_additional_button = ttk.Button(additional_buttons_frame, text="Upload Additional Files", command=load_additional_files)
    load_additional_button.pack(side="left", padx=5)
    
    ttk.Button(additional_buttons_frame, text="Add New File", command=add_new_file).pack(side="left", padx=5)
    ttk.Button(additional_buttons_frame, text="Save Current File", command=save_current_file).pack(side="left", padx=5)
    # Initialize with default template
    on_template_change(None)
    template_var.trace("w", on_template_change)

def cleanup_files(log_widget):
        if not created_files:
            log_message(log_widget, "No files to clean up.")
            return 
        
        for file_path in created_files[:]:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    log_message(log_widget, f"Deleted {file_path}")
                else:
                    log_message(log_widget, f"File {file_path} does not exist.")
            except Exception as e:
                log_message(log_widget, f"Error deleting {file_path}: {e}") 
    
def clear_files_and_exit(window, log_widget):
        log_message(log_widget, "Clearing files and exiting.")
        cleanup_files(log_widget)
        window.quit()

def keep_files_and_exit(window):
     window.quit()
    
def on_close(window, log_widget):
        response = messagebox.askquestion("Exit", "Do you want to clear the files before exiting?", icon='warning')
        if response == "yes":
            clear_files_and_exit(window, log_widget)
        else:
            keep_files_and_exit(window)

def build_docker_image(self):
    app_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    
    # Ensure app directory exists
    if not os.path.exists(app_dir):
        messagebox.showerror("Error", "directory not found")
        return
        
    dockerfile_path = filedialog.askopenfilename(
        initialdir=app_dir,
        title="Select Dockerfile",
        filetypes=[("Dockerfile", "Dockerfile")],
    )
    
    if not dockerfile_path:
        return
        
    # Validate file is within app directory
    if not os.path.commonpath([app_dir]) == os.path.commonpath([app_dir, dockerfile_path]):
        messagebox.showerror("Error", "Please select a Dockerfile from the app directory")
        return

    image_tag = simpledialog.askstring(
        "Image Name/Tag", "Enter image name and tag (e.g., myimage:latest):"
    )
    if not image_tag:
        return

    try:
        cmd = ["docker", "build", "-t", image_tag, "-f", dockerfile_path, app_dir]
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            messagebox.showinfo("Success", f"Image built successfully: {image_tag}")
        else:
            messagebox.showerror("Build Failed", f"Error:\n{stderr}")

    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

def pull_docker_image(log_widget):
    # Step 1: Get the image name from the user
    image_name = simpledialog.askstring("Input", "Enter image name to download (e.g., 'ubuntu:latest'):")

    if not image_name:
        log_message(log_widget, "Operation canceled: No image name provided.")
        return

    try:
        # Step 2: Run the docker pull command
        cmd = f"docker pull {image_name}"

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            # Step 3: Process and display results
            output = stdout.decode('utf-8')
            log_message(log_widget, f"Image '{image_name}' pulled successfully:\n{output}")
            messagebox.showinfo("Success", f"Image '{image_name}' pulled successfully.")
        else:
            # Handle errors if the pull fails
            error_message = stderr.decode('utf-8')
            log_message(log_widget, f"Error pulling image: {error_message}")
            messagebox.showerror("Error", f"Failed to pull image: {error_message}")

    except Exception as e:
        log_message(log_widget, f"Unexpected error: {str(e)}")
        messagebox.showerror("Error", f"Unexpected error: {str(e)}")

def start_container(image_name, container_name):
    """
    Start a Docker container using the given image name and container name.
    
    """
    try:
        # Run the container with the given image name and container name
        container = client.containers.run(
            image_name,
            name=container_name,
            detach=True  # Run container in detached mode
        )
        print(f"Container {container_name} using {image_name} started successfully.")
        messagebox.showinfo("Success", f"Container {container_name} started successfully.")
    except DockerException as e:
        print(f"Error starting container {container_name} with image {image_name}: {e}")
        messagebox.showerror("Error", f"Error starting container: {e}")

def search_local_image(log_widget):
    # Step 1: Get the search term from the user
    image_name = simpledialog.askstring("Input", "Enter image name or tag to search:")
    
    if not image_name:
        log_message(log_widget, "Operation canceled: No image name provided.")
        return

    try:
        # Step 2: Run the docker images command with FINDSTR (Windows) or grep (Linux/Mac)
        cmd = f"docker images | FINDSTR {image_name}"  # Windows command
        # For Linux or Mac, you can use `grep` instead of `FINDSTR`:
        # cmd = f"docker images | grep {image_name}"
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            # Step 3: Process and display results
            output = stdout.decode('utf-8')
            if output:
                log_message(log_widget, f"Search Results for '{image_name}':\n{output}")
                messagebox.showinfo("Success", f"Search completed. Results displayed in log.")
            else:
                log_message(log_widget, f"No local images found matching '{image_name}'.")
                messagebox.showinfo("No Results", f"No images found matching '{image_name}'.")
        else:
            # Handle errors if the search fails
            log_message(log_widget, f"Error: {stderr.decode('utf-8')}")
            messagebox.showerror("Error", f"Search failed: {stderr.decode('utf-8')}")
    except Exception as e:
        log_message(log_widget, f"Unexpected error: {str(e)}")
        messagebox.showerror("Error", f"Unexpected error: {e}")

def search_dockerhub_image(log_widget):
    # Step 1: Get the search term from the user
    image_name = simpledialog.askstring("Input", "Enter image name to search on Docker Hub:")
    
    if not image_name:
        log_message(log_widget, "Operation canceled: No image name provided.")
        return

    try:
        # Step 2: Run the docker search command
        cmd = f"docker search {image_name}"
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            # Step 3: Process and display results
            output = stdout.decode('utf-8')
            log_message(log_widget, f"Search Results for '{image_name}':\n{output}")
            messagebox.showinfo("Success", f"Search completed. Results displayed in log.")
        else:
            # Handle errors if the search fails
            log_message(log_widget, f"Error: {stderr.decode('utf-8')}")
            messagebox.showerror("Error", f"Search failed: {stderr.decode('utf-8')}")
    except Exception as e:
        log_message(log_widget, f"Unexpected error while searching DockerHub: {e}")
        messagebox.showerror("Error", f"Unexpected error: {e}")

def list_docker_images(log_widget):
    log_message(log_widget, "Listing Docker images...")
    images = client.images.list()
    output = "\n".join(f"{image.id[:12]}: {', '.join(image.tags)}" for image in images)
    log_message(log_widget, output if output else "No images found.")

def search_docker_container(log_widget):
    """Search for a specific Docker container."""
    query = simpledialog.askstring("Search Container", "Enter container name or ID to search:")
    if not query:
        return
    try:
        containers = client.containers.list(all=True)
        found = False
        for container in containers:
            if query in container.name or query in container.id:
                log_message(log_widget, f"Found Container: {container.name} | Status: {container.status}")
                found = True
        if not found:
            log_message(log_widget, f"No containers found matching: {query}")
    except Exception as e:
        log_message(log_widget, f"Error: {e}")
        messagebox.showerror("Error", f"Could not search Docker containers: {e}")

def list_running_containers(log_widget):
    log_message(log_widget, "Listing running containers...")
    containers = client.containers.list()
    output = "\n".join(f"{container.id[:12]}: {container.name}" for container in containers)
    log_message(log_widget, output if output else "No running containers found.")

def stop_container(log_widget):
    container_nm =  simpledialog.askstring("Stop Container", "Enter container name:")
    if container_nm:
        try:
            log_message(log_widget, f"Stopping container {container_nm}...")
            # Get the container by name and stop it
            container = client.containers.get(container_nm)
            container.stop()
            log_message(log_widget, f"Container {container_nm} stopped.")
            messagebox.showinfo("Success", f"Container {container_nm} stopped.")
        except docker.errors.NotFound:
            log_message(log_widget, f"Error: Container {container_nm} not found.")
            messagebox.showerror("Error", f"Container {container_nm} not found.")
        except Exception as e:
            log_message(log_widget, f"Error: Failed to stop container: {str(e)}")
            messagebox.showerror("Error", f"Failed to stop container: {str(e)}")

def simple_input_popup(title, prompt):
    popup = tk.Toplevel()
    popup.title(title)
    ttk.Label(popup, text=prompt).pack(pady=10)
    entry = ttk.Entry(popup)
    entry.pack(pady=10, padx=10)

    def submit():
        popup.result = entry.get().strip()
        popup.destroy()

    ttk.Button(popup, text="Submit", command=submit).pack(pady=10)
    popup.mainloop()
    return getattr(popup, 'result', None)

# Main GUI
def main():
    
    root = tk.Tk()
    root.title("Cloud Management System")
    root.geometry("600x600")

    ttk.Label(root, text="Cloud Management System", font=("Times new roman", 16, "bold")).pack(pady=10)
    ttk.Label(root, text="Manage your cloud system with ease.").pack(pady=5)

    button_frame = ttk.Frame(root)
    button_frame.pack(fill="both", expand=True, padx=20, pady=10)

    ttk.Label(root, text="Log Output:").pack(pady=5)
    log_widget = tk.Text(root, wrap="word", width=70, height=15, state="disabled", bg="#f4f4f4")
    log_widget.pack(padx=10, pady=10, fill="both", expand=True)

    ttk.Button(button_frame, text="Create Dockerfile", command=lambda: create_dockerfile(log_widget)).pack(fill="x", pady=5)
    ttk.Button(button_frame, text="Build Docker Image", command=lambda: build_docker_image(log_widget)).pack(fill="x", pady=5)
    ttk.Button(button_frame, text="List Docker Images", command=lambda: list_docker_images(log_widget)).pack(fill="x", pady=5)
    ttk.Button(button_frame, text="Start a container", command=lambda: start_container(simpledialog.askstring("Image Name", "Enter image name:"),
        simpledialog.askstring("Container name", "Enter container name: "))).pack(fill="x", pady=5)
    ttk.Button(button_frame, text="List Running Containers", command=lambda: list_running_containers(log_widget)).pack(fill="x", pady=5)
    ttk.Button(button_frame, text="Stop a Container", command=lambda: stop_container(log_widget)).pack(fill="x", pady=5)
    ttk.Button(button_frame, text="Search Local Image", command=lambda: search_local_image(log_widget)).pack(fill="x", pady=5)
    ttk.Button(button_frame, text="Search DockerHub Image", command=lambda: search_dockerhub_image(log_widget)).pack(fill="x", pady=5)  
    ttk.Button(button_frame, text="Pull Docker Image", command=lambda: pull_docker_image(log_widget)).pack(fill="x", pady=5)
    ttk.Button(button_frame, text="Create QEMU Image", command=lambda: create_image(
        simpledialog.askstring("Image Name", "Enter image name:"),
        simpledialog.askinteger("Size (MB)", "Enter image size in MB:"),
        filedialog.askdirectory(title="Select Save Location")
    )).pack(fill="x", pady=5)
    ttk.Button(button_frame, text="Boot QEMU Image", command=lambda: boot(
        simpledialog.askinteger("RAM (MB)", "Enter RAM size in MB:"),
        simpledialog.askinteger("CPU Cores", "Enter number of cores:"),
        filedialog.askopenfilename(title="Select QEMU Image File"),
        filedialog.askopenfilename(title="Select ISO File (optional)")
    )).pack(fill="x", pady=5)

    root.protocol("WM_DELETE_WINDOW",  lambda:on_close(root, log_widget))
    root.mainloop()

if __name__ == "__main__":
    main()