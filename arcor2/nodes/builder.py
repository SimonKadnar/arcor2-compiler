#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import shutil
import argparse

from typing import Set

from apispec import APISpec  # type: ignore
from apispec_webframeworks.flask import FlaskPlugin  # type: ignore
from flask import Flask, send_file
from dataclasses_jsonschema.apispec import DataclassesPlugin

from arcor2 import persistent_storage as ps
from arcor2.source.logic import program_src, get_logic_from_source
from arcor2.source.utils import derived_resources_class, global_actions_class
from arcor2.source import SourceException
from arcor2.object_types_utils import built_in_types_names
from arcor2.helpers import camel_case_to_snake_case
from arcor2.data.object_type import ObjectModel

PORT = 5007

# Create an APISpec
spec = APISpec(
    title="ARCOR2 Builder Service",
    version="0.0.1",
    openapi_version="3.0.2",
    plugins=[FlaskPlugin(), DataclassesPlugin()],
)

# Dependant schemas are added automatically
# spec.components.schema(IdDescList.__name__, schema=IdDescList)

app = Flask(__name__)

app.config['APISPEC_SPEC'] = spec
app.config['APISPEC_SWAGGER_URL'] = '/swagger/'


@app.route("/project/<string:project_id>/publish", methods=['GET'])
def project_publish(project_id: str):
    """Publish project
            ---
            get:
              description: Get zip file with execution package
              parameters:
                - in: path
                  name: project_id
                  schema:
                    type: string
                  required: true
                  description: unique ID
              responses:
                200:
                  description: Ok
                  content:
                    application/zip:
                        schema:
                          type: string
                          format: binary
                          example: The archive of execution package (.zip)
                404:
                    description: Project ID or some of the required items was not found.
                501:
                    description: Project invalid.
            """

    with tempfile.TemporaryDirectory() as tmpdirname:

        try:
            project = ps.get_project(project_id)
            scene = ps.get_scene(project.scene_id)

            project_dir = os.path.join(tmpdirname, "arcor2_project")

            data_path = os.path.join(project_dir, "data")
            ot_path = os.path.join(project_dir, "object_types")
            srv_path = os.path.join(project_dir, "services")

            os.makedirs(data_path)
            os.makedirs(ot_path)
            os.makedirs(srv_path)

            with open(os.path.join(ot_path, "__init__.py"), "w"):
                pass

            with open(os.path.join(srv_path, "__init__.py"), "w"):
                pass

            with open(os.path.join(data_path, "project.json"), "w") as project_file:
                project_file.write(project.to_json())

            with open(os.path.join(data_path, "scene.json"), "w") as scene_file:
                scene_file.write(scene.to_json())

            obj_types_with_models: Set[str] = set()

            for scene_obj in scene.objects:  # TODO handle inheritance

                obj_type = ps.get_object_type(scene_obj.type)

                if obj_type.model and obj_type.id not in obj_types_with_models:
                    obj_types_with_models.add(obj_type.id)

                    model = ps.get_model(obj_type.model.id, obj_type.model.type)
                    obj_model = ObjectModel(obj_type.model.type, **{model.type().value: model})

                    with open(os.path.join(data_path, camel_case_to_snake_case(obj_type.id) + ".json"), "w")\
                            as model_file:
                        model_file.write(obj_model.to_json())

                with open(os.path.join(ot_path, camel_case_to_snake_case(obj_type.id)) + ".py", "w") as obj_file:
                    obj_file.write(obj_type.source)

            for scene_srv in scene.services:
                srv = ps.get_service_type(scene_srv.type)
                with open(os.path.join(srv_path, camel_case_to_snake_case(srv.id)) + ".py", "w") as srv_file:
                    srv_file.write(srv.source)

        except ps.PersistentStorageException as e:
            return str(e), 404

        try:

            with open(os.path.join(project_dir, 'script.py'), "w") as script:
                script.write(program_src(project, scene, built_in_types_names(), project.has_logic))

            with open(os.path.join(project_dir, 'resources.py'), "w") as res:
                res.write(derived_resources_class(project))

            with open(os.path.join(project_dir, 'actions.py'), "w") as act:
                act.write(global_actions_class(project))

        except SourceException as e:
            return str(e), 501

        archive_path = os.path.join(tmpdirname, "arcor2_project")
        shutil.make_archive(archive_path, 'zip',  project_dir)
        return send_file(archive_path + ".zip")


@app.route("/project/<string:project_id>/script", methods=['PUT'])
def project_script(project_id: str):
    """Project script
            ---
            put:
              description: Add or update project main script
              consumes:
                 - multipart/form-data
              parameters:
                 - in: formData
                   name: upfile
                   type: file
                   description: The file to upload.
              responses:
                200:
                  description: Ok
            """
    # TODO use get_logic_from_source
    pass


with app.test_request_context():
    spec.path(view=project_publish)


def main():

    parser = argparse.ArgumentParser(description='ARCOR2 Project Builder')
    parser.add_argument('-s', '--swagger', action="store_true", default=False)
    args = parser.parse_args()

    if args.swagger:
        print(spec.to_yaml())
        return

    app.run(host='0.0.0.0', port=PORT)


if __name__ == '__main__':
    main()