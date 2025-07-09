# Instructions on installation

When installing stuff anew, please follow these steps to make your life easier:

1. Install `miniconda3`, the procedure should be described [here](https://www.anaconda.com/docs/getting-started/miniconda/install#macos-linux-installation).
2. `conda create -n code-annotation python=3.11` 
3. `conda install mongodb pyyaml -c anaconda` 
4. `python -m pip install flask_pymongo pydantic` 
5. Run Mongo with `mongod --fork --dbpath db/ --logpath mongo.log`, do not use `nohup`.
6. Edit `config.yml` to reflect the specific properties of intended environment.
7. Setup admin's password by running `python setup_admin.py --password yourpassword` and run it.
8. `mkdir -p db/ && rm -r db/*`
9. `nohup python app.py > app.out &`
10. Use login `admin` and password you have entered in (7) to set stuff up: upload data, create users, etc.

You may also need to reinstall `markupsafe` Python package at some point.

Note: admin cannot annotate anything. To annotate, one must create a regular 'Annotator'-level user.