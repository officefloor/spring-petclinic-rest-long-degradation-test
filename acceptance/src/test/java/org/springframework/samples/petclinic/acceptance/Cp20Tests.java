package org.springframework.samples.petclinic.acceptance;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.node.ObjectNode;

/** cp20: persist a derived displayName "Lastname, Firstname" on any owner change. */
@Tag("cp20")
class Cp20Tests extends AcceptanceBase {

	@Test
	void corePersistsDisplayNameOnCreate() throws Exception {
		int id = createOwnerOk(validOwner("John", "Doe"));
		getOwner(id).andExpect(jsonPath("$.displayName").value("Doe, John"));
	}

	@Test
	void functionalityUpdatesDisplayNameOnRename() throws Exception {
		int id = createOwnerOk(validOwner("John", "Doe"));
		ObjectNode upd = validOwner("John", "Smith"); // change last name
		updateOwner(id, upd).andExpect(status().is2xxSuccessful());
		getOwner(id).andExpect(jsonPath("$.displayName").value("Smith, John"));
	}
}
