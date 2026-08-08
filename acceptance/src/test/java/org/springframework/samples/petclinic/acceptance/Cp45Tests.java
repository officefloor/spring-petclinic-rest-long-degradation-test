package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** salutation: The request may include 'title' (MR/MRS/MS/DR). Return 'salutation' = title + ' ' + lastNa... */
@Tag("cp45")
class Cp45Tests extends AcceptanceBase {

	@Test
	void coreComposesSalutation() throws Exception {
		ObjectNode o = structuredOwner();
		o.put("title", "DR"); o.put("lastName", "who");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.salutation").value("DR who"));
	}
}
