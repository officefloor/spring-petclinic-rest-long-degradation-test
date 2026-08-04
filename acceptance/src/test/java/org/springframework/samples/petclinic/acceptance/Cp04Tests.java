package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp04 email-format: An owner may include 'email'. When present it must be a syntactically valid address; store... */
@Tag("cp04")
class Cp04Tests extends AcceptanceBase {

	@Test
	void coreLowercasesEmail() throws Exception {
		ObjectNode o = ownerNode();
		o.put("email", "Test.User@Example.COM");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.email").value("test.user@example.com"));
	}

	@Test
	void errorRejectsInvalidEmail() throws Exception {
		ObjectNode o = ownerNode();
		o.put("email", "not-an-email");
		createOwner(o).andExpect(status().isBadRequest());
	}

	@Test
	void functionalityAcceptsMissingEmail() throws Exception {
		createOwner(ownerNode()).andExpect(status().is2xxSuccessful());
	}
}
